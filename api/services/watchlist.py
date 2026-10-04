# ruff: noqa: E501
"""Saved watchlist: pin a subject to follow it, and see what changed since you last looked.

* A pin is authorised with the same checks as opening the subject (api/access.py): an agent cannot pin another
  agent's customer, a steward cannot pin a customer or case (identity lineage only), and an analyst pins only
  aggregate kinds (cohort, employer, data_product).
* Pins and unpins are written through governance.audit.record (not customer-affecting, but auditable).
* "What changed" is a read-only diff: at each look the facts about the subject (counts from the warehouse and the
  ops store) are saved with the pin (`seen_state_json`); the next look compares the facts now with those.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from fastapi import HTTPException

from api import access
from api.deps import live_data
from api.schemas.common import Session
from api.schemas.watchlist import PinResult, WatchItem, WatchList
from common.config import get_settings
from common.db import OPS_SCHEMA, ops
from common.types import Role
from governance import audit

KINDS = ("customer", "case", "agent", "employer", "cohort", "data_product", "identity")
AGGREGATE_KINDS = {"cohort", "employer", "data_product"}
# who may pin which kind at all (row-level checks come after this)
KIND_ROLES: dict[str, set[Role]] = {
    "customer": {Role.agent, Role.hardship_specialist, Role.team_lead},
    "case": {Role.agent, Role.hardship_specialist, Role.team_lead},
    "agent": {Role.agent, Role.team_lead},
    "employer": {Role.team_lead, Role.analyst},
    "cohort": {Role.team_lead, Role.analyst},
    "data_product": {Role.steward, Role.analyst, Role.team_lead},
    "identity": {Role.steward, Role.agent, Role.hardship_specialist, Role.team_lead},
}
# Cohort ids use the Track pages' format, "<dimension>:<value>", every value checked against a pattern before it is
# bound as a parameter (no protected attribute can be named). bucket and team are extra dimensions here.
COHORT_DIMS: dict[str, tuple[str, str, str]] = {  # dim -> (value pattern, SQL predicate over collections_cases, label)
    "month": (r"20\d\d-(0[1-9]|1[0-2])", "strftime(case_open_date, '%Y-%m') = ?", "Cases opened in {v}"),
    "week": (r"20\d\d-\d\d-\d\d", "date_trunc('week', case_open_date) = CAST(? AS DATE)", "Cases opened in the week of {v}"),
    "province": (r"[A-Z]{2}", "province_code = ?", "Cases in {v}"),
    "fsa": (r"[A-Z]\d[A-Z]", "case_id IN (SELECT k.case_id FROM gold.c360_case k JOIN gold.c360_customer u USING (golden_id) "
                            "WHERE u.fsa = ?)", "Cases in postal area {v}"),
    "strategy": (r"[A-Z][A-Z0-9-]{1,40}", "strategy_code = ?", "Cases on strategy {v}"),
    "product": (r"[a-z_]{2,30}", "primary_product = ?", "Product {v}"),
    "bucket": (r"[0-9a-z+-]{1,10}", "current_bucket = ?", "Bucket {v}"),
    "team": (r"[A-Z]{2,5}(-[A-Z0-9]{1,8}){1,3}", "assigned_team = ?", "Team {v}"),
}
DATA_SCHEMAS = ("gold", "silver", "identity", "features")
_IDENT = re.compile(r"^[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*$")

_ready_paths: set[str] = set()


def _ensure() -> None:
    """Older ops.db files predate the watchlist table: apply the (idempotent) schema once per process."""
    p = str(get_settings().ops_db_path)
    if p in _ready_paths:
        return
    with ops() as con:
        con.executescript(OPS_SCHEMA.read_text())
    _ready_paths.add(p)


def _deny(reason: str) -> HTTPException:
    return HTTPException(403, detail={"reason": reason})


def _q(sql: str, params: list | None = None) -> list[dict]:
    from api.services.c360 import _q as q

    return q(sql, params)


def _parse_cohort(subject_id: str) -> tuple[str, str]:
    """(SQL predicate, value) for a cohort id, or 422."""
    dim, _, val = subject_id.partition(":")
    spec = COHORT_DIMS.get(dim)
    if spec is None or not re.fullmatch(spec[0], val):
        raise HTTPException(422, detail={"reason": "A cohort is <dimension>:<value>, dimension one of "
                                                   f"{', '.join(COHORT_DIMS)} (for example product:card or bucket:31-60)."})
    return spec[1], val


# ------------------------------------------------------------------ authorisation (same checks as viewing)
def authorise(session: Session, kind: str, subject_id: str) -> None:
    """Raise 403 unless this person may open the subject. Same rules as the screens (api/access.py)."""
    role = Role(session.role)
    if kind not in KIND_ROLES:
        raise HTTPException(422, detail={"reason": f"Unknown kind {kind!r}."})
    if role == Role.analyst and kind not in AGGREGATE_KINDS:
        raise _deny("Analysts see aggregates only, so they can follow a cohort, an employer or a data product.")
    if role not in KIND_ROLES[kind]:
        raise _deny(f"The {role.value.replace('_', ' ')} role can't follow a {kind.replace('_', ' ')}.")
    if kind == "customer":
        access.golden(session, subject_id)
    elif kind == "case":
        access.case(session, subject_id)
    elif kind == "identity":
        access.lineage(session, subject_id)
    elif kind == "agent":
        if role == Role.agent and subject_id != session.user_id:
            raise _deny("An agent can follow only their own work, not another agent's.")
        if role == Role.team_lead and live_data():
            if not _q("SELECT 1 FROM silver.agents WHERE agent_id = ? AND team_id = ?", [subject_id, session.team_id]):
                raise _deny("This agent is not on your team.")
    elif kind == "cohort":
        _parse_cohort(subject_id)
    elif kind == "data_product":
        if not _IDENT.match(subject_id) or subject_id.split(".")[0] not in DATA_SCHEMAS:
            raise HTTPException(422, detail={"reason": "A data product is <schema>.<table> in gold, silver or identity."})
    elif kind == "employer" and not re.match(r"^EMP-[0-9A-F]{8}$", subject_id):
        raise HTTPException(422, detail={"reason": "An employer is followed by its radar key (EMP-xxxxxxxx)."})


# ------------------------------------------------------------------ facts about a subject (read-only)
def _flag_now(golden_id: str, warehouse_level: str | None) -> str:
    with ops() as con:
        r = con.execute("SELECT to_level FROM hardship_flag_events WHERE golden_id = ? ORDER BY event_id DESC LIMIT 1", (golden_id,)).fetchone()
    return r["to_level"] if r else (warehouse_level or "none")


def _decisions(where: str, param: str) -> dict[str, int]:
    with ops() as con:
        rows = con.execute(f"SELECT decision, count(*) AS n FROM nba_decisions WHERE {where} = ? GROUP BY 1", (param,)).fetchall()
    d = {r["decision"]: r["n"] for r in rows}
    return {"decisions": sum(d.values()), "overrides": d.get("override", 0) + d.get("edit", 0)}


def _facts_customer(sid: str) -> dict[str, Any]:
    f: dict[str, Any] = {}
    if live_data():
        rows = _q("""SELECT c.hardship_flag, c.vulnerability_flag, c.open_cases,
                            sum(k.contact_attempts_total) AS contacts, sum(k.promises_kept) AS kept,
                            sum(k.promises_broken) AS broken, sum(k.promises_open) AS open_promises
                     FROM gold.c360_customer c LEFT JOIN gold.c360_case k USING (golden_id)
                     WHERE c.golden_id = ? GROUP BY ALL""", [sid])
        if not rows:
            return {"missing": True}
        r = rows[0]
        f = {"contacts": int(r["contacts"] or 0), "kept": int(r["kept"] or 0), "broken": int(r["broken"] or 0),
             "open_promises": int(r["open_promises"] or 0), "open_cases": int(r["open_cases"] or 0),
             "vulnerable": bool(r["vulnerability_flag"]), "_wh_flag": r["hardship_flag"]}
    f["hardship_flag"] = _flag_now(sid, f.pop("_wh_flag", None))
    f.update(_decisions("golden_id", sid))
    return f


def _facts_case(sid: str) -> dict[str, Any]:
    f: dict[str, Any] = {}
    if live_data():
        rows = _q("""SELECT golden_id, case_status, current_dpd, contact_attempts_total, promises_kept, promises_broken,
                            promises_open FROM gold.c360_case WHERE case_id = ?""", [sid])
        if not rows:
            return {"missing": True}
        r = rows[0]
        f = {"golden_id": r["golden_id"], "status": r["case_status"], "dpd": int(r["current_dpd"] or 0),
             "contacts": int(r["contact_attempts_total"] or 0), "kept": int(r["promises_kept"] or 0),
             "broken": int(r["promises_broken"] or 0), "open_promises": int(r["promises_open"] or 0)}
        if r["golden_id"]:
            c = _q("SELECT hardship_flag FROM gold.c360_customer WHERE golden_id = ?", [r["golden_id"]])
            f["hardship_flag"] = _flag_now(r["golden_id"], c[0]["hardship_flag"] if c else None)
    f.update(_decisions("case_id", sid))
    return f


def _facts_agent(sid: str) -> dict[str, Any]:
    f: dict[str, Any] = {}
    if live_data():
        rows = _q("""SELECT agent_display_name, current_case_load, ptp_kept_rate_90d, cure_rate_90d
                     FROM silver.agents WHERE agent_id = ?""", [sid])
        if not rows:
            return {"missing": True}
        r = rows[0]
        f = {"name": r["agent_display_name"], "case_load": int(r["current_case_load"] or 0),
             "kept_rate": r["ptp_kept_rate_90d"], "cure_rate": r["cure_rate_90d"]}
    f.update(_decisions("user_id", sid))
    return f


def _facts_employer(sid: str) -> dict[str, Any]:
    from decisioning import playbooks, radar

    f: dict[str, Any] = {}
    if live_data():
        from common.db import warehouse

        con = warehouse(read_only=True)
        try:
            snap = radar._latest_snapshot(con)
            row = None
            if snap is not None:
                sql = f"SELECT * FROM ({radar.GROUPS_SQL.format(ei=radar.NEW_EI_DAYS, gap=radar.GAP_DAYS)}) g WHERE employer_key = ?"
                rel = con.execute(sql, [snap, snap, sid])
                cols = [d[0] for d in rel.description]
                hit = rel.fetchone()
                row = dict(zip(cols, hit, strict=True)) if hit else None
        finally:
            con.close()
        if row is None:
            return {"missing": True}
        if int(row["n_customers"]) < radar.MIN_GROUP:
            return {"suppressed": True}
        f = {"customers": int(row["n_customers"]), "late_payroll": int(row["n_payroll_gap"]),
             "new_ei": int(row["n_new_ei"]), "open_cases": int(row["open_cases"])}
    f["pending_playbooks"] = sum(1 for p in playbooks.listing(playbooks.PENDING) if p["subject_id"] == sid)
    return f


def _facts_cohort(sid: str) -> dict[str, Any]:
    pred, val = _parse_cohort(sid)
    if not live_data():
        return {}
    r = _q(f"""SELECT count(*) AS cases, count(*) FILTER (WHERE case_status = 'open') AS open_cases,
                      count(*) FILTER (WHERE cure_flag) AS cured, coalesce(sum(promises_broken), 0) AS broken,
                      coalesce(sum(promises_kept), 0) AS kept
               FROM silver.collections_cases WHERE {pred}""", [val])[0]
    if int(r["cases"]) < get_settings().suppression_min_group:
        return {"suppressed": True}
    return {k: int(v or 0) for k, v in r.items()}


def _facts_data_product(sid: str) -> dict[str, Any]:
    from governance import drift

    schema, table = sid.split(".")
    f: dict[str, Any] = {}
    if live_data():
        exists = _q("SELECT 1 FROM information_schema.tables WHERE table_schema = ? AND table_name = ?", [schema, table])
        if not exists:
            return {"missing": True}
        f["rows"] = int(_q(f'SELECT count(*) AS n FROM "{schema}"."{table}"')[0]["n"])
    p = get_settings().reports_dir / "contract_tests.json"
    if p.exists():
        res = json.loads(p.read_text())
        tests = [r for r in res.get("results", []) if str(r.get("unique_id", "")).startswith("test.") and table in r["unique_id"]]
        f["tests"] = len(tests)
        f["tests_failing"] = sum(r.get("status") in ("fail", "error") for r in tests)
    f["drift_pending"] = sum(1 for x in drift.fixes(drift.PENDING) if x["table"] == table)
    return f


def _facts_identity(sid: str) -> dict[str, Any]:
    f: dict[str, Any] = {}
    if live_data():
        rows = _q("SELECT match_method, match_confidence FROM gold.c360_customer WHERE golden_id = ?", [sid])
        if not rows:
            return {"missing": True}
        keys = _q("SELECT count(*) AS n FROM identity.identity_xref WHERE golden_id = ?", [sid])[0]["n"]
        pairs = [r["pair_id"] for r in _q("SELECT pair_id FROM identity.review_queue WHERE candidate_golden_id = ?", [sid])]
        f = {"source_keys": int(keys), "method": rows[0]["match_method"],
             "confidence": None if rows[0]["match_confidence"] is None else round(float(rows[0]["match_confidence"]), 3),
             "pairs": len(pairs)}
        if pairs:
            with ops() as con:
                q = ",".join("?" * len(pairs))
                f["pairs_reviewed"] = con.execute(f"SELECT count(*) FROM identity_reviews WHERE pair_id IN ({q}) AND verdict IS NOT NULL", pairs).fetchone()[0]
        else:
            f["pairs_reviewed"] = 0
    return f


FACTS: dict[str, Callable[[str], dict[str, Any]]] = {
    "customer": _facts_customer, "case": _facts_case, "agent": _facts_agent, "employer": _facts_employer,
    "cohort": _facts_cohort, "data_product": _facts_data_product, "identity": _facts_identity,
}


def facts(kind: str, subject_id: str) -> dict[str, Any]:
    try:
        return FACTS[kind](subject_id)
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001 - one unreadable subject must not break the list
        return {"unreadable": True}


# ------------------------------------------------------------------ describing facts and changes
def _plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n:,} {one if n == 1 else (many or one + 's')}"


def _pct(v) -> str:
    return "n/a" if v is None else f"{float(v) * 100:.0f}%" if float(v) <= 1 else f"{float(v):.0f}%"


def status(kind: str, f: dict[str, Any]) -> str:
    if f.get("missing"):
        return "Not found in the current data."
    if f.get("suppressed"):
        return "Fewer than 10 customers, so the numbers are hidden."
    if f.get("unreadable"):
        return "Can't be read right now."
    parts: list[str] = []
    if kind in ("customer", "case"):
        if "status" in f:
            parts.append(f"case {f['status']}, {f['dpd']} days past due")
        if "contacts" in f:
            parts.append(_plural(f["contacts"], "contact"))
            parts.append(f"promises {f['kept']} kept, {f['broken']} broken, {f['open_promises']} open")
        if f.get("hardship_flag"):
            parts.append(f"hardship flag {f['hardship_flag']}")
    elif kind == "agent":
        if "case_load" in f:
            parts.append(f"{f['case_load']} cases, promises kept {_pct(f['kept_rate'])} (90 days)")
        parts.append(f"{_plural(f.get('decisions', 0), 'decision')} in the app, {f.get('overrides', 0)} changed")
    elif kind == "employer":
        if "customers" in f:
            parts.append(f"{f['customers']} customers, {f['late_payroll']} with late payroll, {f['new_ei']} new EI, {f['open_cases']} open cases")
        parts.append(_plural(f.get("pending_playbooks", 0), "playbook") + " waiting")
    elif kind == "cohort":
        if "cases" in f:
            parts.append(f"{f['open_cases']:,} open of {f['cases']:,} cases, {f['cured']:,} cured, promises {f['kept']:,} kept and {f['broken']:,} broken")
    elif kind == "data_product":
        if "rows" in f:
            parts.append(_plural(f["rows"], "row"))
        if f.get("tests"):
            parts.append(f"{f['tests'] - f['tests_failing']} of {f['tests']} contract tests passing")
        parts.append(_plural(f.get("drift_pending", 0), "drift fix", "drift fixes") + " waiting")
    elif kind == "identity":
        if "source_keys" in f:
            parts.append(f"{_plural(f['source_keys'], 'source key')} linked ({f['method']}, confidence {f['confidence']})")
            parts.append(f"{f['pairs_reviewed']} of {f['pairs']} grey-band pairs reviewed")
    text = "; ".join(parts)
    return text[:1].upper() + text[1:] if text else "No live data loaded."


def _delta(before: dict, now: dict, key: str, up: str, down: str | None = None) -> str | None:
    a, b = before.get(key), now.get(key)
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)) or a == b:
        return None
    d = b - a
    if d > 0:
        return up.format(n=d, a=a, b=b)
    return (down or "{a} to {b}").format(n=-d, a=a, b=b) if down is not None else None


def changes(kind: str, before: dict[str, Any] | None, now: dict[str, Any]) -> list[str]:
    """Plain-English differences between the facts at the last look and now."""
    if not before or now.get("missing") or now.get("unreadable") or now.get("suppressed"):
        return []
    out: list[str | None] = []
    if kind in ("customer", "case"):
        out += [_delta(before, now, "contacts", "{n} new contact(s)"),
                _delta(before, now, "kept", "{n} promise(s) kept"),
                _delta(before, now, "broken", "{n} promise(s) broken"),
                _delta(before, now, "open_promises", "{n} new promise(s) made"),
                _delta(before, now, "decisions", "{n} new decision(s) on the next best action"),
                _delta(before, now, "dpd", "Days past due up from {a} to {b}", "Days past due down from {a} to {b}")]
        if before.get("status") and before.get("status") != now.get("status"):
            out.append(f"Case {before['status']} to {now.get('status')}")
    elif kind == "agent":
        out += [_delta(before, now, "decisions", "{n} new decision(s)"),
                _delta(before, now, "overrides", "{n} new override(s) or edit(s)"),
                _delta(before, now, "case_load", "Case load up from {a} to {b}", "Case load down from {a} to {b}")]
    elif kind == "employer":
        out += [_delta(before, now, "late_payroll", "Late payroll up from {a} to {b}", "Late payroll down from {a} to {b}"),
                _delta(before, now, "new_ei", "{n} more customer(s) with new EI"),
                _delta(before, now, "open_cases", "Open cases up from {a} to {b}", "Open cases down from {a} to {b}"),
                _delta(before, now, "pending_playbooks", "{n} new playbook proposal(s)", "{n} playbook proposal(s) decided")]
    elif kind == "cohort":
        out += [_delta(before, now, "open_cases", "Open cases up from {a} to {b}", "Open cases down from {a} to {b}"),
                _delta(before, now, "cured", "{n} more cured"),
                _delta(before, now, "broken", "{n} more promise(s) broken"),
                _delta(before, now, "kept", "{n} more promise(s) kept")]
    elif kind == "data_product":
        out += [_delta(before, now, "rows", "Rows up from {a:,} to {b:,}", "Rows down from {a:,} to {b:,}"),
                _delta(before, now, "drift_pending", "{n} new schema change(s) waiting (drift)", "{n} drift fix(es) approved"),
                _delta(before, now, "tests_failing", "{n} more contract test(s) failing", "{n} contract test(s) fixed")]
    elif kind == "identity":
        out += [_delta(before, now, "source_keys", "{n} more source key(s) linked", "{n} source key(s) unlinked"),
                _delta(before, now, "pairs_reviewed", "{n} grey-band pair(s) reviewed")]
    if before.get("hardship_flag") and now.get("hardship_flag") and before["hardship_flag"] != now["hardship_flag"]:
        out.append(f"Hardship flag changed from {before['hardship_flag']} to {now['hardship_flag']}")
    return [s.replace("(s)", "s" if not s.startswith("1 ") else "").replace("(es)", "es" if not s.startswith("1 ") else "")
            for s in out if s]


# ------------------------------------------------------------------ links and labels
def link(session: Session, kind: str, sid: str, f: dict[str, Any] | None = None) -> str:
    role = Role(session.role)
    if kind == "customer":
        return f"/customers/{sid}"
    if kind == "case":
        g = (f or {}).get("golden_id")
        return f"/customers/{g}" if g else "/queue"
    if kind == "agent":
        return "/team?tab=agents" if role == Role.team_lead else "/queue"
    if kind == "employer":
        return "/map"
    if kind == "cohort":
        return "/ask"
    if kind == "data_product":
        return "/steward/drift" if role == Role.steward and sid.startswith("silver.") else "/governance/quality"
    if kind == "identity":
        return "/steward/identity" if role == Role.steward else f"/customers/{sid}"
    return "/"


# Track pages (/track/<kind>/<id>) name a data product "product" and follow a case through its customer.
TRACK_KIND = {"customer": "customer", "agent": "agent", "employer": "employer", "cohort": "cohort",
              "identity": "identity", "data_product": "product"}


def track_link(kind: str, sid: str, f: dict[str, Any] | None = None) -> str | None:
    if kind == "case":
        g = (f or {}).get("golden_id")
        return f"/track/customer/{g}" if g else None
    return f"/track/{TRACK_KIND[kind]}/{sid}" if kind in TRACK_KIND else None


def default_label(kind: str, sid: str) -> str:
    if kind == "cohort":
        dim, _, val = sid.partition(":")
        return COHORT_DIMS[dim][2].format(v=val) if dim in COHORT_DIMS else sid
    return {"customer": "Customer", "case": "Case", "agent": "Agent", "employer": "Employer",
            "data_product": "Data product", "identity": "Identity"}[kind] + f" {sid}"


# ------------------------------------------------------------------ store
def _row(session: Session, kind: str, sid: str):
    with ops() as con:
        return con.execute("SELECT * FROM watchlist WHERE user_id = ? AND kind = ? AND subject_id = ?",
                           (session.user_id, kind, sid)).fetchone()


def pins(session: Session) -> list[dict[str, str]]:
    _ensure()
    with ops() as con:
        rows = con.execute("SELECT kind, subject_id FROM watchlist WHERE user_id = ? ORDER BY watch_id", (session.user_id,)).fetchall()
    return [{"kind": r["kind"], "subject_id": r["subject_id"]} for r in rows]


def pin(session: Session, kind: str, sid: str, label: str | None = None) -> PinResult:
    _ensure()
    authorise(session, kind, sid)
    if _row(session, kind, sid) is not None:
        return PinResult(audit_id=None, pinned=True, kind=kind, subject_id=sid)
    f = facts(kind, sid)
    if f.get("missing"):
        raise HTTPException(404, detail={"reason": f"No {kind.replace('_', ' ')} {sid} in the current data."})
    label = (label or "").strip() or default_label(kind, sid)
    audit_id = audit.record(session.user_id, session.role, "watch_pin", kind, sid, {"kind": kind, "subject_id": sid, "label": label})
    with ops() as con:
        con.execute("INSERT OR IGNORE INTO watchlist (user_id, kind, subject_id, label, seen_state_json) VALUES (?,?,?,?,?)",
                    (session.user_id, kind, sid, label, json.dumps(f, default=str)))
    return PinResult(audit_id=audit_id, pinned=True, kind=kind, subject_id=sid)


def unpin(session: Session, kind: str, sid: str) -> PinResult:
    _ensure()
    if _row(session, kind, sid) is None:
        return PinResult(audit_id=None, pinned=False, kind=kind, subject_id=sid)
    audit_id = audit.record(session.user_id, session.role, "watch_unpin", kind, sid, {"kind": kind, "subject_id": sid})
    with ops() as con:
        con.execute("DELETE FROM watchlist WHERE user_id = ? AND kind = ? AND subject_id = ?", (session.user_id, kind, sid))
    return PinResult(audit_id=audit_id, pinned=False, kind=kind, subject_id=sid)


def mark_seen(session: Session, kind: str, sid: str) -> dict[str, Any]:
    _ensure()
    if _row(session, kind, sid) is None:
        raise HTTPException(404, detail={"reason": "You are not following this."})
    f = facts(kind, sid)
    with ops() as con:
        con.execute("""UPDATE watchlist SET last_seen_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'), seen_state_json = ?
                       WHERE user_id = ? AND kind = ? AND subject_id = ?""", (json.dumps(f, default=str), session.user_id, kind, sid))
    return {"ok": True, "kind": kind, "subject_id": sid}


def listing(session: Session) -> WatchList:
    _ensure()
    with ops() as con:
        rows = [dict(r) for r in con.execute("SELECT * FROM watchlist WHERE user_id = ? ORDER BY watch_id DESC", (session.user_id,)).fetchall()]
    items = []
    for r in rows:
        kind, sid = r["kind"], r["subject_id"]
        try:
            authorise(session, kind, sid)
            ok, why = True, None
        except HTTPException as e:
            ok, why = False, (e.detail or {}).get("reason") if isinstance(e.detail, dict) else str(e.detail)
        f = facts(kind, sid) if ok else {}
        before = json.loads(r["seen_state_json"]) if r.get("seen_state_json") else None
        items.append(WatchItem(
            kind=kind, subject_id=sid, label=r["label"] or default_label(kind, sid), created_at=r["created_at"],
            last_seen_at=r["last_seen_at"], link=link(session, kind, sid, f), track_link=track_link(kind, sid, f),
            status=status(kind, f) if ok else f"You can no longer open this: {why}", changes=changes(kind, before, f) if ok else [],
            available=ok))
    return WatchList(items=items, changed=sum(1 for i in items if i.changes))
