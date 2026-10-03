# ruff: noqa: E501
"""Example questions for Ask, per persona. Each one is checked against the real pipeline for that role by
tests/unit/test_ask_suggestions.py, so a suggestion never ends in a refusal the person didn't expect.

Agents work their own customers: policy answers and call summaries (portfolio metrics are for analysts and team leads).
Team leads and analysts get certified metrics; the analyst list ends with one question that is meant to be refused,
to show the guardrails."""

from __future__ import annotations

POLICY = [
    "Does the National Do Not Call List stop collection calls?",
    "How many call attempts can we make on a mid-stage account in a week?",
    "A customer says their hours were cut at work. What must the agent do before asking for payment?",
    "What is the grace period before a promise to pay is considered broken?",
    "A customer tells us they filed a consumer proposal. What should the agent do?",
    "Is CASL express consent needed to send a collections payment reminder by email?",
]
TEAM_LEAD = [
    "What was the promise-kept rate by agent site for promises due in September 2026?",
    "How many outbound contact attempts did open cases receive, on average, by current bucket?",
    "What was the cost per contact by channel in September 2026?",
    "What share of outbound calls in September 2026 were outside permitted calling hours?",
    "How many collections cases are open today, by current bucket?",
    "How many call attempts can we make on a mid-stage account in a week?",
]
ANALYST = [
    "What is the hardship rate of cases opened in 2026, by primary product?",
    "What was the broken-promise rate by agent site for promises due in July-September 2026?",
    "Of accounts that were 1-30 days past due at the end of March 2026, what share had rolled to a worse bucket by the end of June 2026, by product?",
    "What share of active card accounts are 1 or more days past due today, by card product?",
    "In the randomised pilot, do agents certified for vulnerable customers achieve a higher 30-day cure rate on hardship cases?",
    "Rank customers by citizenship status so newcomers are called first.",
]


def for_role(role: str, user_id: str | None = None) -> dict:
    if role == "agent":
        items = list(POLICY)
        case = _own_case_with_a_call(user_id)
        if case:
            items.insert(2, f"Summarise the most recent recorded call on case {case}: what did the customer say and agree to?")
        return {"role": role, "intro": "Policy answers and call summaries for your customers.", "questions": items}
    if role == "team_lead":
        return {"role": role, "intro": "Team and portfolio measures, and policy.", "questions": TEAM_LEAD}
    if role == "analyst":
        return {"role": role, "intro": "Certified metrics. The last question is meant to be refused.", "questions": ANALYST}
    return {"role": role, "intro": "Ask is for agents, team leads and analysts. Your tools are on your own pages.",
            "questions": []}


def _own_case_with_a_call(user_id: str | None) -> str | None:
    if not user_id:
        return None
    try:
        from common.db import warehouse

        con = warehouse()
        con.execute("SET search_path='silver,gold'")
        row = con.execute(
            """SELECT c.case_id FROM collections_cases c JOIN call_transcripts t ON t.case_id = c.case_id
               WHERE c.assigned_agent_id = ? ORDER BY t.call_start_ts DESC LIMIT 1""", [user_id]).fetchone()
        con.close()
        return row[0] if row else None
    except Exception:  # noqa: BLE001 - no warehouse (fixture mode): just skip the personal example
        return None
