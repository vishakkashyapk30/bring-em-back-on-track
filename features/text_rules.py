"""Offline text features (keyword/regex): hardship_signal, stated_delay_reason, dispute_signal,
ptp promise amount/date. Registered as the offline handler for the text_features prompt."""

from __future__ import annotations

import re

from llm.providers.offline import register

HARDSHIP_CLEAR = re.compile(r"\b(laid off|lost (my|his|her) job|unemployed|on ei|employment insurance|"
                            r"medical leave|hospital|disability|bereavement|passed away)\b", re.I)
HARDSHIP_POSSIBLE = re.compile(r"\b(shifts? (cut|reduced)|hours (cut|reduced)|struggling|can'?t afford|"
                               r"reduced income|behind on rent|separation|divorce)\b", re.I)
DISPUTE = re.compile(r"\b(dispute|not my (charge|purchase)|fraud|didn'?t authori[sz]e|wrong amount)\b", re.I)
DELAY_REASONS = {  # TODO(WS-E): align with code_lookups values for stated_delay_reason
    "reduced_income": re.compile(r"\b(shifts?|hours) (cut|reduced)|reduced income|pay cut\b", re.I),
    "job_loss": re.compile(r"\b(laid off|lost (my )?job|unemployed)\b", re.I),
    "payroll_delay": re.compile(r"\b(pay(cheque|check|day)? (is )?late|payroll (delay|late))\b", re.I),
    "medical": re.compile(r"\b(medical|hospital|surgery|sick)\b", re.I),
}


@register("text_features")
def extract_offline(inputs: dict) -> dict:
    text = inputs.get("text", "")
    level = "clear" if HARDSHIP_CLEAR.search(text) else "possible" if HARDSHIP_POSSIBLE.search(text) else "none"
    reason = next((k for k, p in DELAY_REASONS.items() if p.search(text)), None)
    return {"hardship_signal": level, "stated_delay_reason": reason, "ptp_intent_strength": None,
            "dispute_signal": bool(DISPUTE.search(text)), "evidence": []}
