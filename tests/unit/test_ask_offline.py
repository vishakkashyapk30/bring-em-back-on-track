"""Layer 2 offline logic: refusals, time phrases, metric compilation, call-summary template.
These run without a warehouse (pure functions)."""

from datetime import date

import pytest

from features.text_rules import extract, summary
from nlq.refusal import check
from nlq.timeparse import parse
from semantic.compiler import compile_question

AS_OF = date(2026, 9, 28)


@pytest.mark.parametrize("q", [
    "What will the weather be in Toronto tomorrow?",
    "Export the names and phone numbers of every customer in Ontario.",
    "List the gender and marital status of customers who broke a promise last month.",
    "Rank customers by citizenship status so newcomers are called first.",
    "Which postal areas (FSAs) should we stop offering hardship plans to because they default more?",
    "What is the cure rate by age band?",
])
def test_refuses(q):
    assert check(q) is not None


@pytest.mark.parametrize("q", [
    "Is CASL express consent needed to send a collections payment reminder by email?",
    "What should an agent do if a customer discloses a disability?",
    "What was the promise-kept rate for promises due in August 2026?",
])
def test_does_not_refuse(q):
    assert check(q) is None


def test_time_phrases():
    assert (parse("in September 2026", AS_OF).start, parse("in September 2026", AS_OF).end) == (date(2026, 9, 1), AS_OF)
    tr = parse("between 15 and 22 September 2026, compared with the 8 days before", AS_OF)
    assert (tr.start, tr.end, tr.previous.start, tr.previous.end) == (
        date(2026, 9, 15), date(2026, 9, 22), date(2026, 9, 7), date(2026, 9, 14))
    assert parse("last month", AS_OF).start == date(2026, 8, 1)
    assert parse("in the 12 months to 28 September 2026", AS_OF).start == date(2025, 9, 29)


def test_compiles_certified_metric_with_dimension_and_time():
    c = compile_question("What was the broken-promise rate by agent site for promises due in July-September 2026?", AS_OF)
    assert c.metric_id == "broken_promise_rate" and c.dimensions == ["agent_site"]
    assert "ptp_status IN ('kept', 'partially_kept', 'broken')" in c.sql
    assert "BETWEEN DATE '2026-07-01' AND DATE '2026-09-28'" in c.sql


def test_open_cases_use_outcome_is_null():
    c = compile_question("How many collections cases are open today, by current bucket?", AS_OF)
    assert "c.outcome IS NULL" in c.sql and c.dimensions == ["current_bucket"]


def test_unmapped_question_returns_none():
    assert compile_question("Tell me about the weather", AS_OF) is None


def test_call_summary_template():
    turns = [{"speaker": "customer", "text": "I can't pay the whole thing. My hours at work were reduced in Apr."},
             {"speaker": "customer", "text": "Please stop calling me."},
             {"speaker": "agent", "text": "Just to confirm, a payment of $595.00 on Oct 5."}]
    f = extract(turns, date(2026, 9, 20))
    assert f["hardship_reason"] == "reduced_income" and f["cease_request"]
    assert summary(f) == ("Customer reports reduced hours / income; promised $595 on 5 Oct; asked to stop contact; "
                          "next step: stop contact.")
