"""Monitoring snapshot (V1 sections 2 and 10): override rate with the 25% review trigger, the three guardrail counters
that must stay at zero (pressure on customers in hardship, contact-limit breaches, calls outside permitted hours),
refusals, complaints per 1,000 contacts, hardship recall on the labelled sample and data freshness.

Read-only: it reads the ops store (`nba_decisions`, `audit_log`, `hardship_flag_events`), the warehouse (read-only) and
`reports/*.json`, and never writes. The counting rules are pure functions (`override_rate`, `guardrail_counts`) so the
spec suite binds them to its in-memory system and the API binds them to the ops store; both run this code.

PSI drift: not computed. `governance/drift.py` is schema drift (columns and null rates), not a score distribution
comparison, and no scoring-time baseline is stored, so `psi` is reported as None with the reason.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from common.config import get_settings
from common.types import PRESSURE_TREATMENTS

OVERRIDE_REVIEW_THRESHOLD = 0.25  # V1 section 2: "Anything above 25% gets a review"
PRESSURE = {str(t.value) for t in PRESSURE_TREATMENTS}


# ------------------------------------------------------------------ pure counting rules
def override_rate(decisions: Iterable[Mapping[str, Any]]) -> tuple[float | None, int, int]:
    """(rate, decisions reviewed, overrides). A record has `approved_via` ('agent' or 'batch'), `proposed` and `final`
    (None when the person accepted the proposal as is). Only a person's own change on a single decision counts as an
    override; a batch approval accepts the proposal. Rate is None when nothing has been acted on."""
    acted = [d for d in decisions if d.get("approved_via") in ("agent", "batch")]
    over = sum(1 for d in acted if d.get("final") is not None and d.get("approved_via") == "agent"
               and d.get("proposed") != d.get("final"))
    return (over / len(acted) if acted else None), len(acted), over


def guardrail_counts(sent: Iterable[Mapping[str, Any]], out_of_hours: Callable[[Mapping[str, Any]], bool] | None = None
                     ) -> dict[str, int]:
    """Counters that must be 0. A sent record has `treatment`, `channel`, `hardship_flag` ('none' | 'possible' |
    'clear'), `vulnerability_flag`, `contacts_last_7d` (before this one) and `contact_cap_7d`. `out_of_hours(rec)` says
    whether a call broke the permitted hours (the caller decides with the policy gate; None counts none)."""
    pressure = cap = hours = 0
    for m in sent:
        pressure += (str(m.get("treatment")) in PRESSURE
                     and (m.get("hardship_flag", "none") != "none" or bool(m.get("vulnerability_flag"))))
        cap += int(m.get("contacts_last_7d") or 0) + 1 > int(m.get("contact_cap_7d") or 3)
        if m.get("channel") == "call" and out_of_hours is not None:
            hours += bool(out_of_hours(m))
    return {"pressure_on_hardship_count": int(pressure), "contact_cap_breach_count": int(cap),
            "out_of_hours_contact_count": int(hours)}


# ------------------------------------------------------------------ readers (all read-only)
def _action_key(a: Mapping[str, Any] | None) -> tuple | None:
    return None if not a else (a.get("treatment"), a.get("channel"))


def ops_decisions() -> list[dict[str, Any]]:
    """nba_decisions as records for `override_rate`: approve is as proposed; edit and override replace the action."""
    from common.db import ops

    with ops() as con:
        rows = con.execute("SELECT decision, proposed_json, final_json, golden_id, ts FROM nba_decisions").fetchall()
    out = []
    for r in rows:
        prop = (json.loads(r["proposed_json"]) or {}).get("action")
        final = json.loads(r["final_json"]) if r["final_json"] else None
        out.append({"approved_via": "agent", "proposed": _action_key(prop),
                    "final": None if r["decision"] == "approve" else _action_key(final),
                    "final_action": final, "golden_id": r["golden_id"], "ts": r["ts"]})
    return out


def _pressure_on_flagged(decisions: list[dict[str, Any]]) -> int:
    """Decisions whose final action is pressure for a customer whose latest flag event (at that time) was possible or
    clear. Only customers with an event in the ops store are checkable here; the warehouse seed level is not."""
    from common.db import ops

    n = 0
    with ops() as con:
        for d in decisions:
            fa = d.get("final_action") or {}
            if str(fa.get("treatment")) not in PRESSURE or not d.get("golden_id"):
                continue
            ev = con.execute("SELECT to_level FROM hardship_flag_events WHERE golden_id = ? AND ts <= ? "
                             "ORDER BY ts DESC, event_id DESC LIMIT 1", (d["golden_id"], d["ts"])).fetchone()
            n += bool(ev and ev["to_level"] != "none")
    return n


def _refusals() -> int:
    from common.db import ops

    with ops() as con:
        return int(con.execute("SELECT count(*) FROM audit_log WHERE event_type = 'refusal'").fetchone()[0])


def _report(name: str) -> dict | None:
    p = get_settings().reports_dir / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else None


def _complaints_per_1000() -> dict[str, Any]:
    """Complaints raised per 1,000 outbound contacts (the certified contact_count filter), whole history."""
    try:
        from common.db import warehouse

        con = warehouse()
        try:
            n, k = con.execute(
                "SELECT count(*), count(*) FILTER (WHERE complaint_raised_flag) FROM silver.contact_history h "
                "WHERE h.direction = 'outbound' AND coalesce(h.channel_v2, h.channel) <> 'system'").fetchone()
        finally:
            con.close()
    except Exception:  # warehouse not built or table missing: report n/a, do not fail the page
        return {"per_1000": None, "contacts": None, "complaints": None}
    return {"per_1000": round(1000 * k / n, 2) if n else None, "contacts": int(n), "complaints": int(k)}


def freshness_hours() -> float | None:
    p = get_settings().warehouse_path
    return round((time.time() - p.stat().st_mtime) / 3600, 1) if p.exists() else None


# ------------------------------------------------------------------ snapshot
def snapshot(*, decisions: list[Mapping[str, Any]] | None = None, sent: list[Mapping[str, Any]] | None = None,
             refusals: int | None = None, out_of_hours: Callable[[Mapping[str, Any]], bool] | None = None,
             with_warehouse: bool = True) -> dict:
    """The monitoring snapshot. With no arguments it reads the ops store and the warehouse (read-only). The spec suite
    passes its own `decisions`, `sent` and `refusals`, and `with_warehouse=False`."""
    from_ops = decisions is None
    recs = ops_decisions() if from_ops else list(decisions or [])
    rate, reviewed, over = override_rate(recs)
    g = guardrail_counts(sent or [], out_of_hours)
    if from_ops:
        g["pressure_on_hardship_count"] += _pressure_on_flagged(recs)
    text = _report("text_rules_eval") if with_warehouse else None
    fresh = freshness_hours() if with_warehouse else None
    sla = get_settings().freshness_sla_hours
    return {
        "override_rate": rate,
        "override_review_threshold": OVERRIDE_REVIEW_THRESHOLD,
        "override_review_triggered": rate is not None and rate > OVERRIDE_REVIEW_THRESHOLD,
        "decisions_reviewed": reviewed,
        "overrides": over,
        **g,
        "guardrails_ok": not any(g.values()),
        "refusal_count": _refusals() if refusals is None else refusals,
        "complaints": _complaints_per_1000() if with_warehouse else None,
        "hardship_recall": ((text or {}).get("accuracy") or {}).get("hardship_recall"),
        "freshness_hours": fresh,
        "freshness_sla_hours": sla,
        "freshness_ok": fresh is not None and fresh <= sla,
        "psi": None,
        "psi_note": "Not computed: drift.py covers schema drift, and no scoring baseline is stored.",
    }
