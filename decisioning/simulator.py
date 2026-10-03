# ruff: noqa: E501
"""H1 hardship plan simulator, arithmetic only. Never uses household_size / dependants_count.
Outputs: new payment vs monthly surplus; months to clear + total interest; bank impact vs status quo
(discount rate + LGD as stated assumptions); observed hold rate of similar offers ('observed, not causal');
approver level + eligibility. Every run is logged to ops.db simulator_runs + audit_log (by the API layer)."""

from __future__ import annotations

import calendar
from datetime import date

from decisioning import context, eligibility

ASSUMPTIONS = {"annual_discount_rate": 0.06, "lgd": 0.65, "horizon_months": 120}  # TBC, shown on screen
MAX_MONTHS = 600


def _amortised(balance: float, r: float, n: int) -> float:
    return balance / n if r == 0 else balance * r / (1 - (1 + r) ** -n)


def run_schedule(
    balance: float,
    apr: float,
    payment: float,
    holiday: int = 0,
    temp_months: int | None = None,
    temp_apr: float | None = None,
    temp_payment: float | None = None,
) -> dict:
    """Month-by-month: interest accrues; no payment during a holiday; for `temp_months` the temporary APR and payment
    apply (None = the whole plan), after that the normal ones. Returns months, interest and cash flows."""
    bal, interest, flows = balance, 0.0, []
    for m in range(1, MAX_MONTHS + 1):
        temp = temp_months is None or m <= temp_months
        r = (temp_apr if temp and temp_apr is not None else apr) / 12
        pmt = temp_payment if temp and temp_payment is not None else payment
        i = bal * r
        interest += i
        bal += i
        pay = 0.0 if m <= holiday else min(pmt, bal)
        bal -= pay
        flows.append(pay)
        if bal <= 0.005:
            return {"months": m, "interest": interest, "flows": flows, "residual": 0.0}
    return {"months": None, "interest": interest, "flows": flows, "residual": bal}


def _pv(flows: list[float], residual: float, rate: float, a: dict) -> float:
    """Present value of the cash flows. Anything received after the horizon, and any balance still unpaid at the end of
    the schedule, is valued at (1 - LGD) because that far out the bank treats it as at risk."""
    k = (1 + rate) ** (1 / 12) - 1
    h = a["horizon_months"]
    pv = sum((f if i < h else f * (1 - a["lgd"])) / (1 + k) ** (i + 1) for i, f in enumerate(flows))
    return pv + residual * (1 - a["lgd"]) / (1 + k) ** max(len(flows), 1)


def monthly_surplus(income_3m_avg: float | None, essentials_mtd: float | None, other_lenders_mtd: float | None,
                    as_of: date) -> float | None:
    """Income minus essential spend minus other lenders' payments (NI H1). `essential_spend_amount_mtd` is month to
    date and already includes rent, so it is scaled to a full month and housing cost is not subtracted again.
    Other lenders' payments are taken as they stand. Household size and dependants are never inputs."""
    if income_3m_avg is None:
        return None
    days = calendar.monthrange(as_of.year, as_of.month)[1]
    essentials = float(essentials_mtd or 0.0) * days / max(as_of.day, 1)
    return float(income_3m_avg) - essentials - float(other_lenders_mtd or 0.0)


CARD_ONLY_PAYMENT_CUT = ("term_extension_months", "payment_holiday_months", "rate_override", "fee_waiver")


def _lever_set(name: str, value) -> bool:
    if name == "rate_override":
        return value is not None  # 0% (an interest freeze) is a real setting
    return bool(value)


def rejected_levers(product: str, levers: dict) -> list[str]:
    """Cards only get a lower payment (the card payment formula is not defined), so the other levers are refused."""
    if product != "card":
        return []
    return [k for k in CARD_ONLY_PAYMENT_CUT if _lever_set(k, levers.get(k))]


def limits_exceeded(prog: dict, reduction: float, extension: int, rate: float | None, holiday: int,
                    fee_waiver: bool) -> list[str]:
    """Levers that go beyond what the program allows (V1: anything beyond needs a higher approver)."""
    out = []
    max_red = float(prog.get("payment_reduction_pct") or 0.0)
    if reduction > max_red + 1e-9:
        out.append("payment_reduction_pct")
    if extension > int(prog.get("term_extension_max_months") or 0):
        out.append("term_extension_months")
    floor = prog.get("rate_override")
    if rate is not None and (floor is None or floor != floor or rate < float(floor) - 1e-9):
        out.append("rate_override")
    # A payment holiday is a 100% cut for its months, so only a skip-a-payment program (cut = 100%) allows one.
    max_hol = prog.get("max_holiday_months")
    if max_hol is None:
        max_hol = int(prog.get("duration_months") or 0) if max_red >= 1.0 else 0
    if holiday > max_hol:
        out.append("payment_holiday_months")
    if fee_waiver and not prog.get("fees_waived_flag"):
        out.append("fee_waiver")
    return out


def project(
    balance: float,
    apr: float,
    payment_now: float,
    *,
    reduction: float = 0.0,
    extension: int = 0,
    rate: float | None = None,
    holiday: int = 0,
    relief_months: int | None = None,
    fees: float = 0.0,
    waive_fees: bool = False,
    assumptions: dict | None = None,
) -> dict:
    """Pure arithmetic for one scenario against the current contract. `balance` bears interest (principal plus accrued
    interest); `fees` are a separate, non-interest-bearing charge the customer pays unless waived. `relief_months` is
    how long a program's cut/rate/holiday lasts (None = the whole plan); a longer term is always permanent."""
    a = assumptions or ASSUMPTIONS
    base = run_schedule(balance, apr, payment_now)
    new_apr = float(rate) if rate is not None else apr
    after_pay = payment_now
    if extension and base["months"]:
        after_pay = _amortised(balance, new_apr / 12, base["months"] + extension)
    if relief_months and not extension:
        pay = payment_now * (1 - reduction)
        scen = run_schedule(balance, apr, after_pay, holiday, relief_months, new_apr, pay)
    else:
        pay = after_pay * (1 - reduction)
        scen = run_schedule(balance, new_apr, pay, holiday)
    d = a["annual_discount_rate"]
    k = (1 + d) ** (1 / 12) - 1
    fee_pv_base = fees / (1 + k)
    fee_pv_plan = 0.0 if waive_fees else fee_pv_base
    return {
        "base": base,
        "scenario": scen,
        "baseline_payment": payment_now,
        "new_payment": pay,
        "pv_base": _pv(base["flows"], base["residual"], d, a) + fee_pv_base,
        "pv_plan": _pv(scen["flows"], scen["residual"], d, a) + fee_pv_plan,
        "paid_base": sum(base["flows"]) + fees,
        "paid_plan": sum(scen["flows"]) + (0.0 if waive_fees else fees),
    }


def _surplus(golden_id: str) -> float | None:
    from api.services.c360 import _q

    rows = _q(
        """SELECT avg(d.payroll_avg_amount_3m) AS inc, avg(d.essential_spend_amount_mtd) AS ess,
                  avg(d.other_lender_payment_amount_mtd) AS oth
           FROM gold.c360_account a JOIN silver.deposit_accounts d ON d.deposit_account_id = a.account_id
           WHERE a.golden_id = ? AND a.product_type = 'chequing'""",
        [golden_id],
    )
    if not rows or rows[0]["inc"] is None:
        return None
    return monthly_surplus(rows[0]["inc"], rows[0]["ess"], rows[0]["oth"], context.SNAPSHOT)


def _fees_outstanding(golden_id: str, account_id: str) -> float:
    """Unpaid fees on the case's loan account (separate from the balance that bears interest); 0 if not held."""
    from api.services.c360 import _q

    try:
        rows = _q("SELECT fees_outstanding AS f FROM silver.loan_accounts WHERE loan_id = ?", [account_id])
    except Exception:  # noqa: BLE001, the silver layer is optional for the simulator
        return 0.0
    return float(rows[0]["f"] or 0.0) if rows else 0.0


def _hold_rate(program_id: str | None) -> dict | None:
    if not program_id:
        return None
    from api.services.c360 import _q

    r = _q(
        """SELECT count(*) FILTER (WHERE plan_status = 'completed') AS ok, count(*) FILTER (WHERE plan_status IN ('completed','broken')) AS n
              FROM silver.offers WHERE program_id = ? AND customer_response = 'accepted'""",
        [program_id],
    )[0]
    if not r["n"]:
        return None
    return {"value": round(r["ok"] / r["n"], 3), "n": int(r["n"]), "label": "observed, not causal"}


def simulate(case_id: str, levers: dict) -> dict | None:
    rows = context.load_cases(case_id=case_id)
    if not rows:
        return None
    row = rows[0]
    from api.services.c360 import _q

    acct = _q(
        """SELECT a.account_id, a.current_balance, a.interest_rate, a.payment_due, a.product_type
                 FROM gold.c360_case k JOIN gold.c360_account a ON a.account_id = k.primary_account_id WHERE k.case_id = ?""",
        [case_id],
    )
    if not acct or not acct[0]["current_balance"]:
        return {"case_id": case_id, "error": "No balance on the case's main account, so there is nothing to simulate."}
    a = acct[0]
    balance, apr, due = float(a["current_balance"]), float(a["interest_rate"] or 0.0), float(a["payment_due"] or 0.0)
    if due <= 0:
        due = max(balance * 0.03, 25.0)

    programs = context.load_programs()
    prog = next((p for p in programs if p["program_id"] == levers.get("program_id")), None)
    rejected = rejected_levers(a["product_type"], levers)  # explicit levers only; a program brings its own terms
    levers = {**levers, **{k: None if k == "rate_override" else 0 for k in rejected}}
    red = float(levers.get("payment_reduction_pct") or (prog or {}).get("payment_reduction_pct") or 0.0)
    ext = int(levers.get("term_extension_months") or (prog or {}).get("term_extension_max_months") or 0)
    rate = levers.get("rate_override") if levers.get("rate_override") is not None else (prog or {}).get("rate_override")
    hol = int(levers.get("payment_holiday_months") or 0)
    if prog and prog.get("payment_reduction_pct") == 1.0 and not hol:
        hol, red = int(prog.get("duration_months") or 1), 0.0  # "skip a payment" programs are a holiday
    fee = bool(levers.get("fee_waiver") or (prog or {}).get("fees_waived_flag"))
    dur = int(prog["duration_months"]) if prog and prog.get("duration_months") else None
    fees = _fees_outstanding(row["golden_id"], a["account_id"]) if a["product_type"] != "card" else 0.0

    # total_outstanding includes unpaid fees; fees don't bear interest, so they are carried separately
    fees = min(fees, balance)
    p = project(balance - fees, apr, due, reduction=red, extension=ext, rate=rate, holiday=hol, relief_months=dur,
                fees=fees, waive_fees=fee)
    base, scen, pay = p["base"], p["scenario"], p["new_payment"]
    surplus = _surplus(row["golden_id"])

    level = row.get("hardship_flag") or "none"
    elig = (
        eligibility.programs_for(
            row,
            [prog],
            context.load_offer_history([row["golden_id"]]).get(row["golden_id"], []),
            context.SNAPSHOT,
            level,
        )
        if prog
        else []
    )
    if prog:
        beyond = limits_exceeded(prog, red, ext, rate, hol, fee)
        within = bool(elig and elig[0]["eligible"]) and not beyond
        approver = prog["approver_level"]
    else:
        # free-form levers: compare with the most generous agent-level program for this product
        agent_progs = [
            q for q in programs if q["approver_level"] == "agent" and a["product_type"] in str(q["product_types"])
        ]
        cuts = [q for q in agent_progs if (q["payment_reduction_pct"] or 0) < 1.0]
        skips = [q for q in agent_progs if q["payment_reduction_pct"] == 1.0]
        generous = {
            "payment_reduction_pct": max([q["payment_reduction_pct"] or 0 for q in cuts], default=0),
            "term_extension_max_months": max([q["term_extension_max_months"] or 0 for q in agent_progs], default=0),
            "rate_override": min([q["rate_override"] for q in agent_progs if q["rate_override"] is not None], default=None),
            "max_holiday_months": max([int(q["duration_months"] or 0) for q in skips], default=0),
            "fees_waived_flag": any(q["fees_waived_flag"] for q in agent_progs),
        }
        beyond = limits_exceeded(generous, red, ext, rate, hol, fee)
        within, approver = (not beyond), ("agent" if not beyond else "team_lead")

    def shape(s):
        return {"months_to_clear": s["months"], "total_interest": round(s["interest"], 2)}

    return {
        "case_id": case_id,
        "program_id": levers.get("program_id"),
        "within_program": within,
        "approver_level": approver,
        "eligibility": elig[0] if elig else None,
        "beyond_program": beyond,
        "rejected_levers": rejected,
        "inputs": {
            "balance": round(balance, 2),
            "apr": apr,
            "payment_now": round(due, 2),
            "product": a["product_type"],
        },
        "results": {
            "new_payment": round(pay, 2),
            "surplus": None if surplus is None else round(surplus, 2),
            "payment_share_of_surplus": None if not surplus or surplus <= 0 else round(pay / surplus, 2),
            "months_to_clear": scen["months"],
            "months_to_clear_current": base["months"],
            "total_interest": shape(scen)["total_interest"],
            "total_interest_current": shape(base)["total_interest"],
            "payment_holiday_months": hol,
            "fees_waived": fee,
            "bank_impact_vs_status_quo": round(p["pv_plan"] - p["pv_base"], 2),
            "hold_rate_similar": _hold_rate(levers.get("program_id")),
        },
        "assumptions": ASSUMPTIONS,
        "notes": [
            "A program's relief lasts its stated duration, then the normal payment resumes; free-form levers run for the whole plan.",
            "Surplus is monthly income minus essential spend (scaled from month to date to a full month) minus other lenders' payments, an estimate.",
            *([f"Not applied to a card (cards only get a lower payment): {', '.join(rejected)}."] if rejected else []),
        ],
    }
