# ruff: noqa: E501
"""Hardship workbench data: review board, missed offers, eligibility overrides, current flag level."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any

import numpy as np

from api.services.c360 import _meta, _q
from common.config import get_settings
from common.db import ops
from decisioning import context, eligibility

REVIEW_DAYS = 5  # business days (D11, TBC policy)


def current_level(golden_id: str) -> str:
    with ops() as con:
        r = con.execute(
            "SELECT to_level FROM hardship_flag_events WHERE golden_id = ? ORDER BY event_id DESC LIMIT 1", (golden_id,)
        ).fetchone()
    if r:
        return r["to_level"]
    rows = _q("SELECT hardship_flag FROM gold.c360_customer WHERE golden_id = ?", [golden_id])
    return (rows[0]["hardship_flag"] or "none") if rows else "none"


def _due(raised: date) -> date:
    return np.busday_offset(raised, REVIEW_DAYS, roll="forward").astype(date)


def _as_date(v) -> date | None:
    if v is None or v != v or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    return v if isinstance(v, date) else date.fromisoformat(str(v)[:10])


def review_board_rows(customers: Sequence[Mapping[str, Any]], as_of: date) -> list[dict]:
    """H2: customers flagged vulnerable whose review date is due or past, oldest first, with the hardship flag and who
    or what raised it. Uses `vulnerability_flag` only; `vulnerability_type` is protected and never read."""
    out = []
    for c in customers:
        due = _as_date(c.get("vulnerability_review_date"))
        if not c.get("vulnerability_flag") or due is None or due > as_of:
            continue
        out.append(
            {
                "golden_id": c["golden_id"],
                "vulnerability_review_date": due,
                "hardship_flag": c.get("hardship_flag") or "none",
                "hardship_source": c.get("hardship_source"),
            }
        )
    out.sort(key=lambda r: (r["vulnerability_review_date"], r["golden_id"]))
    return out


def _flagged(v) -> bool:
    return v not in (None, False, 0, "", "none", "false", "False")


def missed_offer_report(cases: Sequence[Mapping[str, Any]], offers: Sequence[Mapping[str, Any]]) -> dict:
    """H3: hardship cases never offered a program (newest first), offers made although the rules said no
    (`eligibility_result = ineligible_overridden`), and a count of decline reasons."""
    missed = [
        c
        for c in cases
        if _flagged(c.get("hardship_flag")) and not c.get("hardship_program_offered")
    ]
    missed.sort(key=lambda c: (_as_date(c.get("case_open_date")) or date.min, str(c["case_id"])), reverse=True)
    return {
        "missed": [c["case_id"] for c in missed],
        "overridden_offers": [dict(o) for o in offers if o.get("eligibility_result") == "ineligible_overridden"],
        "decline_reasons": dict(Counter(o["decline_reason"] for o in offers if o.get("decline_reason"))),
    }


def board() -> dict:
    snap = get_settings().as_of_date
    rows = _q("""
        WITH last_mention AS (
            SELECT case_id, max(contact_ts_utc) AS ts FROM silver.contact_history WHERE hardship_mentioned_flag GROUP BY 1)
        SELECT k.golden_id, k.case_id, c.display_name, c.hardship_flag AS level, k.hardship_source AS source,
               k.hardship_reason AS reason, k.current_dpd AS dpd, k.total_overdue,
               CAST(coalesce(m.ts, k.last_contact_ts, k.case_open_date) AS DATE) AS raised
        FROM gold.c360_case k JOIN gold.c360_customer c USING (golden_id) LEFT JOIN last_mention m USING (case_id)
        WHERE k.case_status = 'open' AND c.hardship_flag = 'possible'""")
    items = []
    for r in rows:
        due = _due(r["raised"])
        items.append(
            {
                **r,
                "name": _short(r["display_name"]),
                "raised": str(r["raised"]),
                "review_due": str(due),
                "overdue": due < snap,
                "days_overdue": max((snap - due).days, 0),
            }
        )
    with ops() as con:
        ev = con.execute("""SELECT golden_id, to_level, source, ts FROM hardship_flag_events e
                            WHERE event_id = (SELECT max(event_id) FROM hardship_flag_events x WHERE x.golden_id = e.golden_id)""").fetchall()
    done = {e["golden_id"] for e in ev if e["to_level"] != "possible"}
    items = [i for i in items if i["golden_id"] not in done]
    items.sort(key=lambda i: (not i["overdue"], -i["days_overdue"], -float(i["total_overdue"] or 0)))
    return {
        "meta": _meta(),
        "items": [{k: v for k, v in i.items() if k != "display_name"} for i in items[:300]],
        "total": len(items),
        "overdue": sum(i["overdue"] for i in items),
        "review_days": REVIEW_DAYS,
        "vulnerability_reviews": vulnerability_reviews(snap),
    }


def vulnerability_reviews(as_of: date, limit: int = 100) -> dict:
    """Customers flagged vulnerable whose review date is due or past (NI H2), from `vulnerability_flag` only."""
    rows = _q("""
        SELECT c.golden_id, c.vulnerability_flag, c.vulnerability_review_date, c.hardship_flag,
               (SELECT k.hardship_source FROM gold.c360_case k WHERE k.golden_id = c.golden_id AND k.case_status = 'open'
                ORDER BY k.case_open_date DESC LIMIT 1) AS hardship_source
        FROM gold.c360_customer c WHERE c.vulnerability_flag AND c.vulnerability_review_date <= ?""", [as_of])
    due = review_board_rows(rows, as_of)
    return {
        "total": len(due),
        "items": [{**r, "vulnerability_review_date": str(r["vulnerability_review_date"])} for r in due[:limit]],
    }


def _short(name: str | None) -> str:
    p = (name or "").split()
    return f"{p[0][0]}. {p[-1]}" if len(p) >= 2 else (name or "Customer")


def missed_offers(limit: int = 100) -> dict:
    snap = context.SNAPSHOT
    rows = _q(
        """
        SELECT k.case_id, k.golden_id, c.display_name, c.hardship_flag AS level,
               k.hardship_reason, k.primary_product, k.current_dpd, k.total_overdue, k.case_open_date AS flag_since,
               coalesce(date_diff('month', a.open_date, DATE '2026-09-28'), 0) AS mob
        FROM gold.c360_case k JOIN gold.c360_customer c USING (golden_id)
        LEFT JOIN gold.c360_account a ON a.account_id = k.primary_account_id
        WHERE k.case_status = 'open' AND c.hardship_flag IN ('possible', 'clear')
          AND NOT coalesce(k.hardship_program_accepted, false)
          AND (k.hardship_program_offered IS NULL OR NOT k.hardship_program_offered)
        ORDER BY k.case_open_date DESC, k.total_overdue DESC LIMIT ?""",
        [limit * 3],
    )
    programs = context.load_programs()
    offers = context.load_offer_history([r["golden_id"] for r in rows])
    newest_first = missed_offer_report(  # the same ordering rule the spec suite checks (H3: newest first)
        [{"case_id": r["case_id"], "hardship_flag": r["level"], "hardship_program_offered": False,
          "case_open_date": r["flag_since"]} for r in rows], [])["missed"]
    rows.sort(key=lambda r: newest_first.index(r["case_id"]))
    out = []
    for r in rows:
        case = {
            "primary_product": r["primary_product"],
            "current_dpd": r["current_dpd"],
            "insolvency_hold_flag": False,
            "months_on_book": int(r["mob"]),
        }
        evals = eligibility.programs_for(case, programs, offers.get(r["golden_id"], []), snap, r["level"])
        ok = [e for e in evals if e["eligible"] and e["approver_level"] == "agent"]
        if not ok:
            continue
        out.append(
            {
                "case_id": r["case_id"],
                "golden_id": r["golden_id"],
                "name": _short(r["display_name"]),
                "level": r["level"],
                "hardship_reason": r["hardship_reason"],
                "product": r["primary_product"],
                "dpd": r["current_dpd"],
                "overdue": r["total_overdue"],
                "flag_since": str(r["flag_since"]),
                "eligible_programs": [
                    {"program_id": e["program_id"], "program_name": e["program_name"]} for e in ok[:3]
                ],
            }
        )
        if len(out) >= limit:
            break
    return {
        "meta": _meta(),
        "items": out,
        "note": "Hardship flagged, no program offered yet, and at least one agent-level program fits. Newest first.",
    }


def overrides() -> dict:
    rows = _q("""
        SELECT o.agent_id, a.agent_display_name AS agent_name, o.program_id, count(*) AS count,
               sum(CASE WHEN o.nba_recommended_flag THEN 1 ELSE 0 END) AS nba_recommended
        FROM silver.offers o LEFT JOIN silver.agents a ON a.agent_id = o.agent_id
        WHERE o.eligibility_result = 'ineligible_overridden' AND o.offer_ts <= DATE '2026-09-28'
          AND o.offer_ts >= DATE '2026-09-28' - INTERVAL 180 DAY AND o.offered_by = 'agent'
        GROUP BY ALL ORDER BY count DESC LIMIT 60""")
    return {
        "meta": _meta(),
        "items": rows,
        "window_days": 180,
        "note": "Offers an agent made although the rules said the customer was not eligible.",
    }
