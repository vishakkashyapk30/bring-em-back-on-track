"""Hardship program eligibility, rules only. The LLM never decides eligibility.

Checks per current program (effective_to = 9999-12-31): the product is covered, the customer's hardship level is
at least `min_hardship_level`, days past due <= max_dpd, months on book >= min_months_on_book, uses in the last 12
months < max_uses_12m, not in insolvency (if the program excludes it), no broken plan in the last 90 days (if the
program excludes it). `requires_income_evidence` does not fail a program: it is returned so the person knows to
ask for it. Free text and protected attributes are never inputs.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta

LEVEL = {"none": 0, "possible": 1, "clear": 2}
BROKEN_PLAN_DAYS = 90


def _d(v) -> date | None:
    if v is None or v != v:
        return None
    return v.date() if isinstance(v, datetime) else v


def history_counts(offers: list[dict], program_id: str, as_of: date) -> tuple[int, bool]:
    """(accepted uses of this program in the last 12 months, any broken plan in the last 90 days)."""
    uses, broken = 0, False
    for o in offers:
        ts = _d(o.get("response_ts")) or _d(o.get("offer_ts"))
        if ts is None or ts > as_of or o.get("customer_response") != "accepted":
            continue
        if o.get("program_id") == program_id and ts >= as_of - timedelta(days=365):
            uses += 1
        if o.get("plan_status") == "broken" and ts >= as_of - timedelta(days=BROKEN_PLAN_DAYS):
            broken = True
    return uses, broken


def evaluate(program: dict, case: dict) -> dict:
    """One program against one case. `case`: product, dpd, months_on_book, hardship_level, insolvency, uses_12m,
    broken_plan_90d (the last two for this program)."""
    products = program["product_types"]
    products = json.loads(products) if isinstance(products, str) else list(products or [])
    rules = []

    def add(rule, passed, value, limit, detail=""):
        rules.append({"rule": rule, "passed": bool(passed), "value": value, "limit": limit, "detail": detail})

    add(
        "product_type",
        case["product"] in products,
        case["product"],
        ", ".join(products),
        "The program covers this product",
    )
    add(
        "min_hardship_level",
        LEVEL[case["hardship_level"]] >= LEVEL[program["min_hardship_level"]],
        case["hardship_level"],
        program["min_hardship_level"],
        "Hardship must be at least this level",
    )
    add("max_dpd", case["dpd"] <= program["max_dpd"], case["dpd"], int(program["max_dpd"]), "Days past due at most")
    add(
        "min_months_on_book",
        case["months_on_book"] >= program["min_months_on_book"],
        case["months_on_book"],
        int(program["min_months_on_book"]),
        "Months on book at least",
    )
    add(
        "max_uses_12m",
        case["uses_12m"] < program["max_uses_12m"],
        case["uses_12m"],
        int(program["max_uses_12m"]),
        "Uses in the last 12 months must be below this",
    )
    # Every rule is always shown (the screen shows which passed or failed); a rule the program doesn't use passes.
    excl_ins, excl_broken = bool(program["excludes_insolvency"]), bool(program["excludes_broken_plan_90d"])
    add(
        "excludes_insolvency",
        not (excl_ins and case["insolvency"]),
        bool(case["insolvency"]),
        False,
        "Not available in insolvency" if excl_ins else "This program does not exclude insolvency",
    )
    add(
        "excludes_broken_plan_90d",
        not (excl_broken and case["broken_plan_90d"]),
        bool(case["broken_plan_90d"]),
        False,
        "Not available after a broken plan in the last 90 days"
        if excl_broken
        else "This program does not exclude a recent broken plan",
    )
    red = program.get("payment_reduction_pct")
    return {
        "program_id": program["program_id"],
        "program_name": program["program_name"],
        "eligible": all(r["passed"] for r in rules),
        "approver_level": program["approver_level"],
        "payment_reduction_pct": None if red is None or red != red else float(red),
        "duration_months": None if program.get("duration_months") is None else int(program["duration_months"]),
        "fees_waived_flag": bool(program.get("fees_waived_flag")),
        "requires_income_evidence": bool(program["requires_income_evidence"]),
        "rules": rules,
        "decided_by": "rules",
    }


def programs_for(
    row: dict, programs: list[dict], offers: list[dict], as_of: date, hardship_level: str | None = None
) -> list[dict]:
    """Every program for the case's product, evaluated. `row` is a decisioning.context case row."""
    level = hardship_level or row.get("hardship_flag") or "none"
    out = []
    for p in programs:
        prods = p["product_types"]
        prods = json.loads(prods) if isinstance(prods, str) else list(prods or [])
        if row["primary_product"] not in prods:
            continue
        uses, broken = history_counts(offers, p["program_id"], as_of)
        out.append(
            evaluate(
                p,
                {
                    "product": row["primary_product"],
                    "dpd": int(row["current_dpd"]),
                    "months_on_book": int(row.get("months_on_book") or 0),
                    "hardship_level": level,
                    "insolvency": bool(row.get("insolvency_hold_flag")),
                    "uses_12m": uses,
                    "broken_plan_90d": broken,
                },
            )
        )
    return out


def check(case_id: str) -> dict | None:
    """Eligibility for every program that covers the case's product, for the live case page."""
    from decisioning import context

    rows = context.load_cases(case_id=case_id)
    if not rows:
        return None
    row = rows[0]
    offers = context.load_offer_history([row["golden_id"]]).get(row["golden_id"], [])
    progs = programs_for(row, context.load_programs(), offers, context.SNAPSHOT)
    progs.sort(key=lambda p: (not p["eligible"], p["program_id"]))
    return {"case_id": case_id, "hardship_level": row.get("hardship_flag") or "none", "programs": progs}
