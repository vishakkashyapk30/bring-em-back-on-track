# ruff: noqa: E501
"""NBA orchestration: open cases -> policy gate -> risk -> ladder -> allocator -> explanation.

`build_queue` runs the whole book nightly (python -m decisioning.nba) and writes data/features/nba_queue.parquet;
`propose` recomputes one case live (so a hardship flag raised a minute ago changes the answer at once) and returns
the full explanation. Both call the same `decide`, so the queue and the case page cannot disagree.
"""

from __future__ import annotations

import json
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from common.config import get_settings
from decisioning import allocator, context, eligibility, explain, ladder, policy_gate
from decisioning.schemas import Action, GateResult

CFG = yaml.safe_load((Path(__file__).parent / "config.yaml").read_text())
TREATMENTS = ["reminder", "payment_link", "plan_offer", "specialist_referral"]
CHANNELS = ["call", "sms", "email", "push", "letter"]
BAND_START = {"08-12": time(8), "12-17": time(12), "17-21": time(17), "all_day": time(9)}
FALLBACK_COST = {"call": 2.4, "sms": 0.01, "email": 0.001, "push": 0.001, "letter": 1.1}
BATCHABLE = {
    ("reminder", "sms"),
    ("reminder", "email"),
    ("reminder", "push"),
    ("payment_link", "sms"),
    ("payment_link", "email"),
    ("payment_link", "push"),
}


def queue_path() -> Path:
    return get_settings().features_dir / "nba_queue.parquet"


def _hm(s: str) -> time:
    h, m = s[:5].split(":")
    return time(int(h), int(m))


def _window(channel: str, treatment: str, customer: dict) -> str:
    """Time band for an action. Calls go in the evening when the customer's hours allow it, then afternoon, then
    morning; digital reminders go out in the morning, payment links after lunch."""
    if channel == "letter":
        return "all_day"
    if channel != "call":
        return "08-12" if treatment == "reminder" else "12-17"
    start, end = _hm(customer["permitted_call_start_local"]), _hm(customer["permitted_call_end_local"])
    for band in ("17-21", "12-17", "08-12"):
        if start <= max(BAND_START[band], start) < end and BAND_START[band] < end:
            return band
    return "12-17"


def _alt_windows(customer: dict, planned: str) -> list[str]:
    """Other call windows that overlap the customer's permitted hours, in order of preference."""
    start, end = _hm(customer["permitted_call_start_local"]), _hm(customer["permitted_call_end_local"])
    spans = {"17-21": (time(17), time(21)), "12-17": (time(12), time(17)), "08-12": (time(8), time(12))}
    return [b for b, (s, e) in spans.items() if b != planned and start < e and end > s]


def _scheduled(plan_date: date, band: str, customer: dict) -> datetime:
    tz = ZoneInfo(customer["time_zone"])
    start = BAND_START[band]
    if customer.get("permitted_call_start_local"):
        start = max(start, _hm(customer["permitted_call_start_local"]))
    return datetime.combine(plan_date, start, tzinfo=tz)


def candidates(customer: dict, plan_date: date) -> list[Action]:
    out = []
    for t in TREATMENTS:
        for ch in CHANNELS:
            band = _window(ch, t, customer)
            out.append(Action(treatment=t, channel=ch, window=band, scheduled_at=_scheduled(plan_date, band, customer)))
    return out


def _mask(name: str | None) -> str:
    parts = (name or "").split()
    return f"{parts[0][0]}. {parts[-1]}" if len(parts) >= 2 else (name or "Customer")


def _pick_program(
    row: dict, programs: list[dict], offers: list[dict], as_of: date
) -> tuple[str | None, str | None, list[dict]]:
    evals = eligibility.programs_for(row, programs, offers, as_of)
    ok = [e for e in evals if e["eligible"] and e["approver_level"] == "agent"]
    ok.sort(key=lambda e: -(e["payment_reduction_pct"] or 0))
    return (ok[0]["program_id"], ok[0]["program_name"], evals) if ok else (None, None, evals)


def decide(
    row: dict,
    programs: list[dict] | None = None,
    offers: list[dict] | None = None,
    plan_date: date | None = None,
    feature_age_hours: float = 0.0,
) -> dict:
    """The whole decision for one case row. Returns action, gate result, ladder reasons and the pieces the
    explanation needs."""
    plan_date = plan_date or get_settings().as_of_date
    customer = policy_gate.customer_from_row(row)
    cands = candidates(customer, plan_date)
    at = cands[0].scheduled_at
    g = policy_gate.gate(customer, cands, at, feature_age_hours)
    p = row.get("p_break")
    p = None if p is None or p != p else float(p)
    action, reasons = ladder.choose(row, p, g, CFG, plan_date)
    program_name, evals = None, None
    if action.treatment == "plan_offer" and programs is not None:
        pid, program_name, evals = _pick_program(row, programs, offers or [], plan_date)
        action = action.model_copy(update={"program_id": pid})
    return {
        "customer": customer,
        "gate": g,
        "action": action,
        "reasons": reasons,
        "p_break": p,
        "program_name": program_name,
        "eligibility": evals,
    }


def _review_mode(row: dict, action: Action, g: GateResult) -> str:
    """Plan offers, calls and anything touching hardship or vulnerability are reviewed one by one; routine digital
    reminders and payment links can be approved as a batch after a 2% sample."""
    t = action.treatment.value
    ch = action.channel.value if action.channel else None
    if g.route_to or t in ("plan_offer", "specialist_referral") or ch == "call":
        return "individual"
    return "batch" if (t, ch) in BATCHABLE else "individual"


def _capacity(plan_date: date) -> tuple[dict, dict, dict]:
    import duckdb

    con = duckdb.connect(str(get_settings().warehouse_path), read_only=True)
    try:
        cap = {
            (c, b): int(n)
            for c, b, n in con.execute(
                "SELECT channel, time_band, capacity_units FROM silver.channel_capacity WHERE date = ? AND NOT outage_flag",
                [plan_date],
            ).fetchall()
        }
        cost = {
            c: float(v)
            for c, v in con.execute(
                "SELECT channel, avg(unit_cost_cad) FROM silver.channel_capacity WHERE date = ? GROUP BY 1", [plan_date]
            ).fetchall()
        }
        slots = {
            a: int(n or 0)
            for a, n in con.execute(
                "SELECT agent_id, sum(outbound_call_capacity) FROM silver.agent_shifts WHERE shift_date = ? AND NOT absence_flag GROUP BY 1",
                [plan_date],
            ).fetchall()
        }
    finally:
        con.close()
    return cap, {**FALLBACK_COST, **cost}, slots


def build_queue(date_: str | None = None) -> list[dict]:
    """Decide every open case and allocate capacity. One dict per case."""
    import numpy as np

    plan_date = date.fromisoformat(date_) if date_ else get_settings().as_of_date
    rows = context.load_cases()
    programs = context.load_programs()
    plan_ids = [
        r["golden_id"] for r in rows if r.get("last_broken_ts") is not None and (r.get("payroll_delay_days") or 0) > 0
    ]
    offers = context.load_offer_history(plan_ids)
    cap_amount = float(np.percentile([r["total_overdue"] for r in rows], 75))
    capacity, cost, slots = _capacity(plan_date)
    out = []
    for r in rows:
        d = decide(r, programs, offers.get(r["golden_id"], []), plan_date)
        a, g = d["action"], d["gate"]
        t = a.treatment.value
        ch = a.channel.value if a.channel else None
        pr = (
            0.0
            if t == "no_contact"
            else allocator.priority(d["p_break"], float(r["total_overdue"]), cap_amount, cost.get(ch or "", 0.0), CFG)
        )
        out.append(
            {
                "case_id": r["case_id"],
                "golden_id": r["golden_id"],
                "name": _mask(r["display_name"]),
                "product": r["primary_product"],
                "dpd": int(r["current_dpd"]),
                "bucket": r["current_bucket"],
                "overdue": float(r["total_overdue"]),
                "treatment": t,
                "channel": ch,
                "window": a.window.value if a.window else None,
                "program_id": a.program_id,
                "priority": pr,
                "p_break": d["p_break"],
                "risk_band": r.get("risk_band"),
                "hardship_flag": r.get("hardship_flag") or "none",
                "vulnerable": bool(r.get("vulnerability_flag")),
                "route_to": g.route_to,
                "review_mode": _review_mode(r, a, g),
                "headline": d["reasons"][0].text if d["reasons"] else "",
                "assigned_agent_id": r.get("assigned_agent_id"),
                "assigned_team": r.get("assigned_team"),
                "queue": r.get("queue"),
                "plan_date": str(plan_date),
                "alt_windows": _alt_windows(d["customer"], a.window.value) if ch == "call" and a.window else [],
            }
        )
    allocator.allocate(out, capacity, slots)
    return out


def main() -> None:
    import pandas as pd

    rows = build_queue()
    df = pd.DataFrame(rows)
    path = queue_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    summary = df.groupby(["treatment", "status"]).size().unstack(fill_value=0)
    print(f"wrote {path} ({len(df)} cases)")
    print(summary.to_string())
    make_batches(df)


def sample_size(n_items: int) -> int:
    """How many items of a batch a person checks first: 2% rounded up, never fewer than one (V1 section 6)."""
    import math

    return min(n_items, max(1, math.ceil(n_items * CFG["batch"]["sample_pct"]))) if n_items else 0


def uplift_gate(overlap_share: float, cases_per_action: dict[str, int]) -> tuple[bool, str]:
    """Phase 2 (uplift) runs only if at least 70% of open cases have comparable history and every action has at least
    1,000 cases; otherwise the rules stay and we say uplift cannot be measured yet (V1 section 6). Returns
    (enabled, reason)."""
    u = CFG["uplift"]
    if overlap_share < u["min_overlap_share"]:
        return False, (
            f"Only {overlap_share:.0%} of open cases have comparable history (need {u['min_overlap_share']:.0%}): "
            "the rules stay, uplift cannot be measured yet"
        )
    thin = sorted(a for a, n in cases_per_action.items() if n < u["min_cases_per_action"])
    if thin:
        return False, (
            f"{', '.join(a.replace('_', ' ') for a in thin)} has under {u['min_cases_per_action']:,} cases: "
            "the rules stay, uplift cannot be measured yet"
        )
    return True, "Comparable history and enough cases for every action: uplift can be measured"


def make_batches(df) -> int:
    """Group routine digital actions into batches for the team lead (2% sample first). Pending batches are
    rebuilt each night; approved ones are kept."""
    from common.db import ops

    plan = str(df.plan_date.iloc[0]).replace("-", "")
    b = df[(df.review_mode == "batch") & (df.status == "scheduled")]
    n = 0
    with ops() as con:
        con.execute("DELETE FROM batches WHERE status = 'pending' AND batch_id LIKE ?", (f"B-{plan}-%",))
        for (team, treatment, channel), g in b.groupby(["assigned_team", "treatment", "channel"], dropna=False):
            g = g.sort_values("priority", ascending=False)
            sample = g.sample(n=sample_size(len(g)), random_state=7)
            bid = f"B-{plan}-{channel.upper()}-{treatment[:3].upper()}-{team or 'POOL'}"
            con.execute(
                "INSERT OR IGNORE INTO batches (batch_id, kind, strategy_code, items_json, sample_json) VALUES (?,?,?,?,?)",
                (
                    bid,
                    "digital_reminders",
                    f"{treatment}:{channel}",
                    json.dumps(g.case_id.tolist()),
                    json.dumps(sample.case_id.tolist()),
                ),
            )
            n += 1
    return n


def propose(case_id: str) -> dict | None:
    """Live proposal for one case, with the full explanation."""
    rows = context.load_cases(case_id=case_id)
    if not rows:
        return None
    r = rows[0]
    programs = context.load_programs()
    offers = context.load_offer_history([r["golden_id"]]).get(r["golden_id"], [])
    d = decide(r, programs, offers)
    a, g = d["action"], d["gate"]
    alts = alternatives(d, r)
    ex = explain.explain(a, g, d["reasons"], r, d["customer"], d["p_break"], alts, context.SNAPSHOT, d["program_name"])
    q = None
    if queue_path().exists():
        import pandas as pd

        qq = pd.read_parquet(queue_path(), filters=[("case_id", "==", case_id)])
        q = qq.iloc[0].to_dict() if len(qq) else None
    priority = float(q["priority"]) if q is not None else 0.0
    return {
        "case_id": case_id,
        "golden_id": r["golden_id"],
        "action": a.model_dump(mode="json"),
        "priority": priority,
        "explanation": ex.model_dump(mode="json"),
        "route_to": g.route_to,
        "review_mode": _review_mode(r, a, g),
        "status": None if q is None else q["status"],
        "deferred_reason": None if q is None or q["deferred_reason"] != q["deferred_reason"] else q["deferred_reason"],
    }


def audit_proposal(
    case_id: str,
    treatment: str,
    channel: str | None,
    p_break: float | None,
    rule_codes: list[str],
    user_id: str,
    role: str,
) -> int:
    """Log that a score and a proposed action were produced for a case (V1 section 10: every score and decision is
    audited). Only codes and the action go in, never free text or customer details."""
    from governance import audit

    return audit.record(
        user_id,
        role,
        "score",
        "case",
        case_id,
        {"case_id": case_id},
        {"treatment": treatment, "channel": channel, "p_break": p_break, "rules": rule_codes},
    )


def alternatives(d: dict, row: dict) -> list[dict]:
    """Other options the person could pick, and why each was not chosen."""
    g: GateResult = d["gate"]
    chosen = d["action"]
    out = []
    shown = set()
    for t, ch in [
        ("payment_link", "sms"),
        ("reminder", "push"),
        ("reminder", "call"),
        ("plan_offer", "call"),
        ("specialist_referral", "call"),
    ]:
        if t == chosen.treatment.value and ch == (chosen.channel.value if chosen.channel else None):
            continue
        if t in shown:
            continue
        allowed = g.permits(t, ch)
        if allowed:
            why = "Allowed, but the ladder prefers the recommended action for this case"
        else:
            why = g.reason_for(t, ch) or "Not allowed by the contact rules"
        shown.add(t)
        out.append({"action": {"treatment": t, "channel": ch}, "why_not": why, "allowed": allowed})
        if len(out) == 4:
            break
    return out


if __name__ == "__main__":
    main()
