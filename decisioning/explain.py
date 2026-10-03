"""Deterministic explanation template: recommendation, rules applied, model evidence (labelled
'model estimate'), what changed, freshness, alternatives. No LLM."""

from __future__ import annotations

import json
from datetime import date

from decisioning.policy_gate import CHANNEL_LABEL
from decisioning.schemas import Action, Explanation, GateResult, ReasonCode

WINDOW_TEXT = {
    "08-12": "between 8 am and noon",
    "12-17": "between noon and 5 pm",
    "17-21": "between 5 pm and 9 pm",
    "all_day": "at any time of day",
}
BAND_LABEL = {"low": "Low", "medium": "Medium", "high": "High", "very_high": "Very high"}


def _when(a: Action) -> str:
    w = a.window.value if hasattr(a.window, "value") else a.window
    if w not in WINDOW_TEXT:
        return ""
    return f", {WINDOW_TEXT[w]}" + ("" if w == "all_day" else " local time")


def recommendation(a: Action, route_to: str | None = None, program_name: str | None = None) -> str:
    t = a.treatment.value if hasattr(a.treatment, "value") else a.treatment
    ch = a.channel.value if hasattr(a.channel, "value") else a.channel
    label = CHANNEL_LABEL.get(ch or "", ch or "")
    if t == "no_contact":
        return "No contact for now"
    if t == "reminder":
        return (
            f"Call about the payment{_when(a)}"
            if ch == "call"
            else f"Send a reminder by {label}{_when(a)}"
        )
    if t == "payment_link":
        return f"Send a payment link by {label}{_when(a)}"
    if t == "plan_offer":
        what = program_name or "a payment arrangement"
        return f"Offer {what} by {label}{_when(a)}"
    if t == "specialist_referral":
        who = "a hardship specialist" if route_to == "hardship_specialist" else "a trained agent"
        return f"Hand over to {who} by {label}{_when(a)}, with no pressure"
    return t.replace("_", " ")


def positives(gate_result: GateResult, customer: dict, a: Action) -> list[ReasonCode]:
    """Rules the chosen action passed, so the person sees what was checked, not only what blocked."""
    ch = a.channel.value if hasattr(a.channel, "value") else a.channel
    if a.treatment == "no_contact" or not ch:
        return []
    out = []
    if ch in ("call", "sms", "email", "push"):
        out.append(ReasonCode(code="CONSENT_OK", text=f"Consent on file for {CHANNEL_LABEL[ch]}", kind="rule"))
    used, cap = int(customer.get("contacts_last_7d") or 0), int(customer.get("contact_cap_7d") or 3)
    out.append(ReasonCode(code="CAP_7D_OK", text=f"{used} of {cap} contacts used this week", kind="rule"))
    if ch == "call":
        s, e = customer.get("permitted_call_start_local", "08:00"), customer.get("permitted_call_end_local", "20:00")
        out.append(
            ReasonCode(code="HOURS_OK", text=f"Within call hours ({s[:5]} to {e[:5]} local time)", kind="rule")
        )
    return out


def drivers(case: dict, p_break: float | None) -> list[ReasonCode]:
    out: list[ReasonCode] = []
    reasons = case.get("reasons") or (json.loads(case["reasons_json"]) if case.get("reasons_json") else [])
    for r in reasons:
        out.append(
            ReasonCode(
                code=r["code"],
                text=r["text"][:1].upper() + r["text"][1:],
                kind="model",
                contribution=r.get("contribution"),
            )
        )
    pd_ = case.get("payroll_delay_days")
    if pd_ and pd_ > 0:
        out.append(ReasonCode(code="payroll_delay_days", text=f"Payroll arrived {int(pd_)} days late", kind="signal"))
    if (case.get("nsf_count_mtd") or 0) >= 2:
        out.append(
            ReasonCode(
                code="nsf_count_mtd", text=f"{int(case['nsf_count_mtd'])} payments returned this month", kind="signal"
            )
        )
    return out


def changes(case: dict, as_of: date) -> list[ReasonCode]:
    out = []
    lb = case.get("last_broken_ts")
    if lb is not None and lb == lb:
        d = lb.date() if hasattr(lb, "date") else lb
        pid = case.get("last_broken_ptp")
        which = f"Promise {pid}" if pid else "A promise"
        out.append(ReasonCode(code="PTP_BROKEN", text=f"{which} was broken on {d:%-d %b}", kind="change"))
    if case.get("hardship_source") == "set in the app":
        out.append(ReasonCode(code="HARDSHIP_SET", text="A person set the hardship flag in the app", kind="change"))
    return out


def explain(
    action: Action,
    gate_result: GateResult,
    reasons: list[ReasonCode],
    case: dict,
    customer: dict,
    p_break: float | None,
    alternatives: list[dict],
    as_of: date,
    program_name: str | None = None,
) -> Explanation:
    band = case.get("risk_band")
    model = case.get("risk_model")
    if p_break is None:
        evidence = {
            "p_break": None,
            "band": None,
            "label": "No promise score for this case",
            "model": None,
            "drivers": [],
        }
    else:
        evidence = {
            "p_break": round(float(p_break), 3),
            "band": band,
            "label": "model estimate",
            "model": model,
            "drivers": [d.model_dump() for d in drivers(case, p_break)],
        }
    # Rules: the ladder's reason first, then what the chosen action passed, then what else was ruled out.
    seen, rules = set(), []
    contacting = action.treatment != "no_contact"
    for r in [*reasons, *positives(gate_result, customer, action), *gate_result.rules_fired]:
        if r.code in seen:
            continue
        if contacting and r.code.startswith("NO_CONSENT_"):
            continue  # a channel we did not pick: its missing consent is noise
        seen.add(r.code)
        rules.append(r)
    chg = changes(case, as_of)
    return Explanation(
        recommendation=recommendation(action, gate_result.route_to, program_name),
        rules_applied=rules,
        model_evidence=evidence,
        what_changed=chg,
        freshness=ReasonCode(code="FRESH", text=f"Data from {as_of:%-d %b %Y}", kind="freshness"),
        alternatives=alternatives,
        generated_by="template",
    )
