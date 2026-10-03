"""Question -> semantic layer -> guarded SQL -> answer with SQL, sources and caveats, or a refusal
(Brief Layer 2; V1 §4)."""

from __future__ import annotations

import datetime as dt
import re

import pytest

from tests_spec import factories as F
from tests_spec import spec_constants as C
from tests_spec.adapter import UserContext

pytestmark = pytest.mark.sql_guard

PTP_Q = "Which customers are most likely to break a promise to pay this week?"


def test_answer_sql_passes_the_guard_for_the_same_user(loaded, analyst_user):
    """V1 §4 step 3: MetricFlow writes the query and the checker validates it; the SQL shown must be the
    SQL that ran, and it must pass the same guard."""
    ans = loaded.ask(PTP_Q, analyst_user)
    assert not ans.refused and ans.sql
    assert loaded.validate_sql(ans.sql, analyst_user).ok


def test_answer_names_gold_data_products_and_is_fresh(loaded, analyst_user):
    """Brief takeaway "Every answer carries its SQL and the data products it used"; V1 §4 step 5 "how
    fresh the data is"; contract freshness SLA 26 h."""
    ans = loaded.ask(PTP_Q, analyst_user)
    assert any(p.startswith("gold.") for p in ans.data_products), ans.data_products
    assert ans.freshness is not None
    assert F.AS_OF - ans.freshness <= dt.timedelta(hours=C.FRESHNESS_SLA_HOURS)


@pytest.mark.s5
def test_pre_flight_reports_portfolio_coverage(loaded, analyst_user):
    """V1 §4 step 4 (S5): "Each answer says how much of the portfolio it covers"."""
    ans = loaded.ask(PTP_Q, analyst_user)
    assert ans.coverage is not None
    assert 0 <= ans.coverage.rows_or_customers <= ans.coverage.portfolio_total


@pytest.mark.s5
@pytest.mark.h5
def test_incident_in_the_period_is_flagged(loaded, analyst_user):
    """V1 §4 step 4 (S5): "flags incidents in the period, such as the 14 Sep app outage"; v2 caveats
    include "any ops_events in range"."""
    ans = loaded.ask("How many promises to pay were broken between 10 Sep and 20 Sep 2026?", analyst_user)
    assert not ans.refused
    assert C.OUTAGE_INCIDENT_ID in ans.incidents or any(C.OUTAGE_INCIDENT_ID in c or "outage" in c.lower() for c in ans.caveats)


@pytest.mark.s5
def test_no_incident_flag_outside_the_incident_window(loaded, analyst_user):
    """V1 §4 step 4 (S5): only incidents *in the period* are flagged."""
    ans = loaded.ask("How many promises to pay were broken between 1 Oct and 5 Oct 2026?", analyst_user)
    assert not ans.refused
    assert C.OUTAGE_INCIDENT_ID not in ans.incidents


def test_refusal_returns_no_sql_and_no_rows(loaded, analyst_user):
    """Brief Layer 2 "Refusal of questions outside allowed data"; V1 §8 refusals are plain rules."""
    ans = loaded.ask("List the phone numbers and dates of birth of customers at Lakeshore Auto Parts", analyst_user)
    assert ans.refused and not ans.rows


@pytest.mark.rbac
def test_agent_answers_only_cover_their_own_cases(loaded):
    """V1 §4 step 3 "applies the user's row filter"; v2 §4 "Agents see their own cases
    (assigned_agent_id)"."""
    agent2 = UserContext(user_id="agent-002", role="agent", team_id="team-b")
    ans = loaded.ask("Show my open cases with a broken promise", agent2)
    if ans.refused:
        pytest.skip("question refused for agents in this binding")
    case_ids = {r.get("case_id") for r in ans.rows if r.get("case_id")}
    assert "CASE-RYM-0001" not in case_ids  # assigned to agent-001


@pytest.mark.rbac
@pytest.mark.governance
def test_analyst_rows_are_aggregates_with_small_groups_suppressed(loaded, analyst_user):
    """v2 §4: "analysts aggregates with groups under 10 suppressed"; V1 §10 masking."""
    ans = loaded.ask("Broken promise rate by employer this month", analyst_user)
    if ans.refused:
        return
    for r in ans.rows:
        assert "display_name" not in r and "primary_phone_e164" not in r
        n = r.get("n_customers") or r.get("customer_count")
        if n is not None:
            assert n >= C.SMALL_GROUP_MIN_SIZE


@pytest.mark.audit
def test_every_question_is_audited(loaded, analyst_user):
    """V1 §10: "An append-only audit log records every query"."""
    loaded.ask(PTP_Q, analyst_user)
    loaded.ask("What is the cure rate by gender?", analyst_user)
    recs = [r for r in loaded.audit_log(event_type="query") if r.actor_id == analyst_user.user_id]
    assert len(recs) >= 2, "answered and refused questions are both logged"


@pytest.mark.governance
def test_raw_pii_is_never_sent_to_the_llm(loaded, analyst_user):
    """V1 Part 3 Not allowed "Sending raw PII to an external LLM"; v2 §7 Hosting "production uses a
    bank-hosted model with PII masked"."""
    loaded.ask(PTP_Q, analyst_user)
    loaded.ask("Why is G-004817 high risk?", analyst_user)
    for req in loaded.llm_request_log():
        for raw in ("+15195550142", "ryan.m@example.test", F.RYAN_NID, "1985-04-12"):
            assert raw not in req.prompt_text, f"raw PII {raw!r} sent for {req.purpose}"


def test_insight_uses_only_returned_rows(loaded, analyst_user):
    """V1 §4 step 5 "A written summary uses only those rows": an empty result must not produce an insight
    that cites numbers."""
    ans = loaded.ask("Which customers broke a promise to pay on 1 January 2019?", analyst_user)
    if ans.refused or ans.rows:
        pytest.skip("needs an answered question with an empty result")
    assert not re.search(r"\d", ans.insight_text or ""), ans.insight_text
