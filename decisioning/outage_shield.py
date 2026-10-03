"""H5 outage-victim shield: do not chase or charge customers because of the bank's own outage.

Accounts due during an ops_events outage window that paid the next day are candidates for a fee reversal and a hold on
pressure actions. Both are proposals that wait for a team lead (decisioning/playbooks.py stores and approves them).

It is a candidate list, not a final answer: the time a payment was attempted exists only in `transactions.txn_ts`, which
covers a customer sample, so elsewhere the shield infers from the due date and the paid date. The count is compared with
the bank's own estimate (`ops_events.affected_customers_est`). Rules only, so it works with LLM_PROVIDER=offline.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

NOTE = ("Candidate list, not a final answer: payment attempt times exist only for a sample of customers, so "
        "'paid the next day' is inferred from the due date and the paid date.")
POSTING_TABLES = {"card_statements", "loan_instalments", "promises_to_pay"}


def _get(e: Any, key: str, default: Any = None) -> Any:
    return e.get(key, default) if isinstance(e, Mapping) else getattr(e, key, default)


def _tables(e: Any) -> set[str]:
    t = _get(e, "affected_tables") or []
    if isinstance(t, str):
        t = [x.strip(' "[]') for x in t.split(",")]
    return {str(x) for x in t}


def is_payment_outage(event: Any) -> bool:
    """An outage window in which payments did not post (ops_events): explicit flag, else the type and the text."""
    flag = _get(event, "payment_posting_affected")
    if flag is not None and "outage" in str(_get(event, "event_type", "")).lower():
        return bool(flag)
    kind = str(_get(event, "event_type", "")).lower()
    text = str(_get(event, "description", "")).lower()
    return "outage" in kind and (bool(_tables(event) & POSTING_TABLES) or "payment" in text or "post" in text)


def _d(v: Any) -> dt.date | None:
    return v.date() if isinstance(v, dt.datetime) else v


def victims(event: Any, repayments: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """The candidate list and the two proposals per candidate. `repayments` rows: account_id, golden_id, due_date,
    paid_date, fees_charged, fees_reversed (a due item and when it was paid)."""
    start, end = _d(_get(event, "start_ts")), _d(_get(event, "end_ts"))
    cands = [r for r in repayments
             if r.get("paid_date") is not None and start <= _d(r["due_date"]) <= end
             and _d(r["paid_date"]) == _d(r["due_date"]) + dt.timedelta(days=1)]
    props: list[dict[str, Any]] = []
    for r in cands:
        owed = (r.get("fees_charged") or 0) - (r.get("fees_reversed") or 0)
        if owed > 0:
            props.append({"proposal_id": f"PR-FEE-{r['account_id']}", "kind": "fee_reversal",
                          "subject_id": r["account_id"], "golden_id": r.get("golden_id"),
                          "detail": f"Reverse fees of {owed:.2f} "
                                    f"CAD on {r['account_id']}: it was due during {_get(event, 'event_id')} and paid "
                                    "the next day."})
    for gid in sorted({r.get("golden_id") for r in cands if r.get("golden_id")}):
        props.append({"proposal_id": f"PR-HOLD-{gid}", "kind": "pressure_hold", "subject_id": gid, "golden_id": gid,
                      "detail": f"Hold pressure actions for {gid}: an account was due during "
                                f"{_get(event, 'event_id')}."})
    ids = [r["account_id"] for r in cands]
    return {"event_id": _get(event, "event_id"), "candidates": ids, "our_count": len(ids),
            "bank_estimate": _get(event, "affected_customers_est"), "is_candidate_list": True, "note": NOTE,
            "proposals": props, "members": sorted({r["golden_id"] for r in cands if r.get("golden_id")})}


def outage_events(con) -> list[dict[str, Any]]:
    rows = con.execute("SELECT event_id, event_type, description, affected_tables, affected_customers_est, "
                       "start_ts, end_ts FROM silver.ops_events ORDER BY start_ts").fetchall()
    keys = ("event_id", "event_type", "description", "affected_tables", "affected_customers_est", "start_ts", "end_ts")
    return [e for e in (dict(zip(keys, r, strict=True)) for r in rows) if is_payment_outage(e)]


def _table(con, name: str, cols: str, where: str, params: Sequence[Any]) -> list[tuple]:
    """Read a silver table; on a machine where its view points at the container path, read the bronze parquet."""
    try:
        return con.execute(f"SELECT {cols} FROM silver.{name} WHERE {where}", list(params)).fetchall()
    except Exception:  # noqa: BLE001 (duckdb IOException when /app/data is absent)
        from common.config import get_settings

        path = get_settings().bronze_dir / f"{name}.parquet"
        if not path.exists():
            return []
        import duckdb

        local = duckdb.connect()
        try:
            return local.execute(f"SELECT {cols} FROM read_parquet('{path}') WHERE {where}", list(params)).fetchall()
        finally:
            local.close()


def repayments_from_warehouse(con, event: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Due items from card_statements, loan_instalments and promises_to_pay that fell in the outage window."""
    s, e = _d(event["start_ts"]), _d(event["end_ts"])
    gid: dict[str, str] = {}

    def golden(ids: list[str], system: str) -> None:
        if not ids:
            return
        q = ",".join("?" for _ in ids)
        for a, g in con.execute(f"SELECT account_id, golden_id FROM identity.account_xref WHERE source_system = ? "
                                f"AND account_id IN ({q})", [system, *ids]).fetchall():
            gid[a] = g

    out: list[dict[str, Any]] = []
    cards = _table(con, "card_statements",
                   "card_account_id, due_date, first_payment_after_due_date, fees_amount, fees_reversed_amount",
                   "due_date BETWEEN ? AND ?", [s, e])
    loans = _table(con, "loan_instalments", "loan_id, due_date, paid_date, fee_component",
                   "due_date BETWEEN ? AND ?", [s, e])
    ptps = con.execute("SELECT account_id, ptp_due_date, paid_date FROM silver.promises_to_pay "
                       "WHERE ptp_due_date BETWEEN ? AND ?", [s, e]).fetchall()
    golden(sorted({c[0] for c in cards}), "cards")
    golden(sorted({c[0] for c in loans} | {p[0] for p in ptps if p[0] and str(p[0]).startswith("L-")}), "lending")
    golden(sorted({p[0] for p in ptps if p[0] and str(p[0]).startswith("C-")}), "cards")
    for a, due, paid, fee, rev in cards:
        out.append({"account_id": a, "golden_id": gid.get(a), "due_date": due, "paid_date": paid,
                    "fees_charged": fee or 0.0, "fees_reversed": rev or 0.0, "source": "card_statements"})
    for a, due, paid, fee in loans:
        out.append({"account_id": a, "golden_id": gid.get(a), "due_date": due, "paid_date": paid,
                    "fees_charged": fee or 0.0, "fees_reversed": 0.0, "source": "loan_instalments"})
    seen = {r["account_id"] for r in out}
    for a, due, paid in ptps:  # a promise due in the window and paid the next day also counts
        if a and a not in seen:
            out.append({"account_id": a, "golden_id": gid.get(a), "due_date": due, "paid_date": paid,
                        "fees_charged": 0.0, "fees_reversed": 0.0, "source": "promises_to_pay"})
    return out


def candidates(event_id: str | None = None, con=None) -> list[dict[str, Any]]:
    """Reports for the outage window(s) of the real warehouse (read only). One report per payment outage event."""
    from common.db import warehouse

    own = con is None
    con = con or warehouse(read_only=True)
    try:
        events = [e for e in outage_events(con) if event_id in (None, e["event_id"])]
        reports = []
        for ev in events:
            rep = victims(ev, repayments_from_warehouse(con, ev))
            chased = con.execute("SELECT count(DISTINCT crm_customer_id) FROM silver.contact_history "
                                 "WHERE ops_incident_id = ?", [ev["event_id"]]).fetchone()[0]
            rep.update(description=ev["description"], start_ts=str(ev["start_ts"]), end_ts=str(ev["end_ts"]),
                       customers_contacted_during_incident=chased)
            reports.append(rep)
        return reports
    finally:
        if own:
            con.close()
