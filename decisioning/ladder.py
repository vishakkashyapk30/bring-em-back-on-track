# ruff: noqa: E501
"""Treatment ladder (rules). Phase 1 NBA = rules informed by risk, not uplift (D2).

Order (first match wins, as settled in docs/profiling_decisions.md), after the policy gate has removed what must not be done:
 1. Hardship or vulnerability: specialist referral (never pressure), or no contact while an agreed hardship plan runs.
 2. A promise just broke and the customer's pay is late: a plan offer (help before nudging).
 3. 31+ days past due and high risk: a call from an agent.
 4. A promise is open, the risk is high and it falls due within 3 days: a reminder.
 5. A promise is open and the risk is low: no contact, the promise is on track.
 6. An open promise that is not due soon: no contact yet, look again closer to the date.
 7. Otherwise: a payment link.
If the chosen treatment has no channel the gate permits, the ladder tries the other pressure-free-of-conflict
treatment once, then does nothing and says why.
"""

from __future__ import annotations

from datetime import date

from decisioning.schemas import Action, GateResult, ReasonCode

DIGITAL = ["push", "sms", "email"]
PREFERENCE = {
    "reminder": DIGITAL + ["call", "letter"],
    "payment_link": ["sms", "email", "push"],
    "plan_offer": ["call", "sms", "email"],
    "specialist_referral": ["call", "sms", "email", "push", "letter"],
}
AGENT_CALL = ["call"]


def risk_band(p: float | None, cfg: dict) -> str | None:
    if p is None:
        return None
    return "low" if p < cfg["risk"]["low_max"] else ("high" if p >= cfg["risk"]["high_min"] else "medium")


def _rc(code: str, text: str) -> ReasonCode:
    return ReasonCode(code=code, text=text, kind="rule")


def _pick(gate_result: GateResult, treatment: str, channels: list[str]) -> Action | None:
    for ch in channels:
        for a in gate_result.allowed:
            if a.treatment == treatment and a.channel == ch:
                return a
    return None


def _days_to_due(case: dict, as_of: date) -> int | None:
    d = case.get("ptp_due_date")
    if d is None or d != d:
        return None
    d = d.date() if hasattr(d, "date") else d
    return (d - as_of).days


def desired(
    case: dict, p_break: float | None, gate_result: GateResult, cfg: dict, as_of: date
) -> tuple[str, list[str], ReasonCode]:
    """(treatment, preferred channels, the rule that picked it)."""
    band = risk_band(p_break, cfg)
    open_ptp = bool(case.get("ptp_id") == case.get("ptp_id") and case.get("ptp_id"))
    due = _days_to_due(case, as_of)
    dpd = int(case.get("current_dpd") or 0)
    just_broken = False
    lb = case.get("last_broken_ts")
    if lb is not None and lb == lb:
        lb = lb.date() if hasattr(lb, "date") else lb
        just_broken = (as_of - lb).days <= cfg["broken_lookback_days"]
    delayed = (case.get("payroll_delay_days") or 0) > 0

    plan_end = case.get("hardship_plan_end")
    if (
        gate_result.route_to == "hardship_specialist"
        and case.get("hardship_program_accepted")
        and plan_end is not None
        and (plan_end.date() if hasattr(plan_end, "date") else plan_end) >= as_of
    ):
        return (
            "no_contact",
            [],
            _rc("LADDER_ON_PLAN", "This customer is on an agreed hardship plan, so we won't contact them while the plan runs"),
        )
    if gate_result.route_to in ("hardship_specialist", "vulnerable_customer_certified"):
        why = (
            "This customer has a hardship flag"
            if gate_result.route_to == "hardship_specialist"
            else "This customer is flagged as vulnerable"
        )
        return (
            "specialist_referral",
            PREFERENCE["specialist_referral"],
            _rc("LADDER_REFERRAL", f"{why}, so a trained agent should handle it, without pressure"),
        )
    if just_broken and delayed:
        return (
            "plan_offer",
            PREFERENCE["plan_offer"],
            _rc("LADDER_BROKEN_LATE_PAY", "They broke a recent promise and their pay is late, so offer a payment plan before another reminder"),
        )
    if dpd >= cfg["dpd_agent_call_min"] and (band == "high" or band is None):
        basis = "and likely to break a promise" if band == "high" else "with no promise on the case"
        return (
            "reminder",
            AGENT_CALL,
            _rc("LADDER_AGENT_CALL", f"They're {cfg['dpd_agent_call_min']}+ days past due {basis}, so an agent should call"),
        )
    if open_ptp and band == "high" and due is not None and due <= cfg["due_soon_days"]:
        return (
            "reminder",
            PREFERENCE["reminder"],
            _rc(
                "LADDER_PTP_DUE_SOON",
                f"Their promise is due within {cfg['due_soon_days']} days and may well break, so send a reminder",
            ),
        )
    if open_ptp and band == "low":
        return (
            "no_contact",
            [],
            _rc("LADDER_PTP_ON_TRACK", "They've made a promise and are unlikely to break it, so no contact is needed"),
        )
    if open_ptp:
        return (
            "no_contact",
            [],
            _rc("LADDER_PTP_WAIT", "They've made a promise that isn't due yet, so wait and look again closer to the date"),
        )
    return "payment_link", PREFERENCE["payment_link"], _rc("LADDER_DEFAULT", "There is no open promise, so send a payment link")


def choose(
    case: dict, p_break: float | None, gate_result: GateResult, cfg: dict, as_of: date | None = None
) -> tuple[Action, list[ReasonCode]]:
    """Return (action, reason codes) for one case."""
    from common.config import get_settings

    as_of = as_of or get_settings().as_of_date
    if gate_result.disposition != "contact_allowed":
        why = gate_result.rules_fired[:1] or [_rc("GATE_BLOCK", "Contact is not allowed")]
        return Action(treatment="no_contact"), list(why)
    treatment, channels, rule = desired(case, p_break, gate_result, cfg, as_of)
    if treatment == "no_contact":
        return Action(treatment="no_contact"), [rule]
    action = _pick(gate_result, treatment, channels)
    if action is None and treatment in ("reminder", "payment_link"):
        other = "payment_link" if treatment == "reminder" else "reminder"
        action = _pick(gate_result, other, PREFERENCE[other])
        if action is not None:
            return action, [
                rule,
                _rc(
                    "LADDER_FALLBACK",
                    f"No permitted channel for a {treatment.replace('_', ' ')}: used a {other.replace('_', ' ')} instead",
                ),
            ]
    if action is None and treatment == "plan_offer":
        # a plan needs a person: fall back to a call-less referral rather than a pressure treatment
        action = _pick(gate_result, "specialist_referral", PREFERENCE["specialist_referral"])
    if action is None:
        blockers = [r for r in gate_result.rules_fired if r.code != "HARDSHIP_NO_PRESSURE"][:2]
        return Action(treatment="no_contact"), [
            rule,
            *(blockers or [_rc("NO_CHANNEL", "No channel is permitted right now")]),
        ]
    return action, [rule]
