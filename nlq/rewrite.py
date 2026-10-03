# ruff: noqa: E501
"""LLM question understanding for Ask (optional; the rules in semantic/compiler.py run first and always work).

When the rules don't recognise a question, a language model (local Ollama or Gemini, set by LLM_PROVIDER) rewrites it
into the wording of one certified metric. The rewrite goes back through the same refusal rules, the same compiler and
the same SQL guard as a typed question, so the model can only choose among certified metrics: it never writes SQL,
never sees customer rows, and its choice is checked (the compiled metric must be the one it named).
With LLM_PROVIDER=offline this step returns nothing and Ask behaves exactly as before.
"""

from __future__ import annotations

import re
from datetime import date

from common.config import get_settings
from common.llm_mode import effective_provider
from llm.providers.offline import register

# metric id -> (what it measures, sample wording that the compiler recognises). Checked by a unit test.
CATALOGUE: dict[str, tuple[str, str]] = {
    "cure_rate": ("share of cases that returned to current within 30 days", "What is the cure rate of cases opened in August 2026?"),
    "roll_rate": ("share of accounts in a bucket at one date that rolled to a worse bucket by a later date",
                  "Of accounts that were 1-30 days past due at the end of March 2026, what share had rolled to a worse bucket by the end of June 2026?"),
    "promise_kept_rate": ("share of resolved promises to pay that were kept", "What was the promise-kept rate for promises due in August 2026?"),
    "broken_promise_rate": ("share of resolved promises to pay that were broken", "What was the broken-promise rate for promises due in July 2026?"),
    "broken_promise_count": ("number of broken promises", "How many broken promises were there in July 2026?"),
    "kept_promise_count": ("number of kept promises", "How many promises were kept in July 2026?"),
    "paid_against_promises": ("money paid against promises / collected amount", "How much was paid against promises in September 2026?"),
    "ptp_rate": ("promises made per right-party contact", "What was the PTP rate by agent site in September 2026?"),
    "rpc_rate": ("share of outbound call attempts that reached the right party", "What was the right-party contact rate on outbound calls in September 2026?"),
    "cost_per_contact": ("average cost of a contact attempt", "What was the cost per contact by channel in September 2026?"),
    "cost_per_rpc": ("cost per right-party contact", "What was the cost per right-party contact by channel in September 2026?"),
    "contact_count": ("number of outbound contacts / calls / sms / emails made", "How many outbound calls did we make on 25 September 2026?"),
    "contact_attempts_per_case": ("average outbound attempts per case", "How many outbound contact attempts did open cases receive on average by current bucket?"),
    "out_of_hours_share": ("share of outbound calls made outside permitted hours", "What share of outbound calls in September 2026 were outside permitted calling hours?"),
    "average_dpd": ("average days past due of open cases", "What is the average days past due of open cases by queue?"),
    "average_overdue": ("average amount past due of open cases", "What is the average amount past due on open cases by bucket?"),
    "open_case_count": ("number of open collections cases", "How many collections cases are open today by current bucket?"),
    "case_count": ("number of collections cases opened in a period", "How many cases were opened in September 2026 by product?"),
    "hardship_rate": ("share of cases flagged hardship", "What is the hardship rate of cases opened in 2026 by primary product?"),
    "cases_on_hardship_plan": ("open cases that accepted a hardship plan", "How many cases are on a hardship plan today?"),
    "delinquency_rate": ("share of active card accounts past due", "What share of active card accounts are 1 or more days past due today by card product?"),
    "loan_delinquency_rate": ("share of loan accounts past due (personal, auto, mortgage, line of credit)", "What is the delinquency rate for personal loans today?"),
    "write_off": ("accounts charged off and the amount, in a period", "How many accounts were charged off in the 12 months to 28 September 2026 by product?"),
    "dispute_count": ("number of disputes raised", "How many late-fee disputes were raised between 15 and 22 September 2026?"),
    "complaint_count": ("number of complaints raised", "How many complaints were raised in September 2026?"),
    "payroll_delay_share": ("share of customers with payroll more than 7 days late", "What share of customers have payroll more than 7 days late?"),
}

# Words that mean the question wants something the data can't give. Checked before and after the model.
NOT_MEASURABLE = re.compile(
    r"\b(forecast\w*|predict\w*|will|would|projected|tomorrow|next (week|month|quarter|year)|revenue|profit\w*|"
    r"satisf\w*|handle time|talk time|wait time|nps|net promoter|headcount|on shift|shifts?)\b", re.I)
GENERIC = {"what", "which", "how", "many", "much", "average", "typical", "number", "share", "rate", "total", "percentage",
           "proportion", "fraction", "split", "breakdown", "list", "show", "tell", "give", "have", "the", "did", "does",
           "was", "were", "are", "our", "out", "for", "and", "per", "cases", "case", "customers", "accounts", "month",
           "year", "last", "this", "today", "current", "during", "than", "that", "with", "from", "into", "over", "all"}


def _words(text: str) -> set[str]:
    return {w[:5] for w in re.findall(r"[a-z]{3,}", text.lower()) if w not in GENERIC}


def grounded(question: str, metric_id: str) -> bool:
    """The model's pick must share at least one meaningful word with the metric's own description (so a related-sounding
    but different measure, or a guess, is thrown away) and the question must not ask for something unmeasurable."""
    if NOT_MEASURABLE.search(question):
        return False
    measures, sample = CATALOGUE[metric_id]
    return bool(_words(question) & _words(f"{measures} {sample} {SYNONYM_HINTS.get(metric_id, '')}"))


# Everyday words for each metric that the description above doesn't contain.
SYNONYM_HINTS = {
    "rpc_rate": "reached picked answered phoned called connected contact rate", "average_dpd": "late behind overdue arrears file",
    "promise_kept_rate": "honoured honored fulfilled kept", "broken_promise_rate": "defaulted dishonoured reneged broken",
    "paid_against_promises": "money brought collected recovered received payments", "open_case_count": "files outstanding live active",
    "case_count": "came new opened intake", "write_off": "written charged off losses", "cost_per_contact": "cost try reaching spend",
    "ptp_rate": "promise taken agreed committed", "cure_rate": "recovered returned current cured back", "contact_count": "texts messages sent made",
    "average_overdue": "behind owed outstanding balance", "loan_delinquency_rate": "late overdue arrears delinquent loans",
}


@register("question_rewrite")
def rewrite_offline(inputs: dict) -> dict:
    return {"measure": "", "metric_id": None, "reason": "offline: rules only"}


def choose_metric(question: str, as_of: date | None = None) -> dict | None:
    """{"metric_id", "measure"} chosen by the LLM and verified, or None (no LLM configured, unreachable, or declined)."""
    if effective_provider() == "offline" or NOT_MEASURABLE.search(question):
        return None
    from llm.client import complete_json

    out = complete_json(
        "question_rewrite", 1,
        {"question": question, "as_of_date": str(as_of or get_settings().as_of_date),
         "metrics": [{"id": k, "measures": v[0], "sample": v[1]} for k, v in CATALOGUE.items()]},
        "question_rewrite")
    mid = out.get("metric_id")
    if out.get("_meta", {}).get("provider") == "offline" or mid not in CATALOGUE or not grounded(question, mid):
        return None
    return {"metric_id": mid, "measure": str(out.get("measure", ""))}
