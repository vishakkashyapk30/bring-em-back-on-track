"""Rephrasings the released benchmark does not contain (eval/probe/questions.csv). Ask must route each one to the
right certified metric (checked on the compiled SQL, no warehouse needed), refuse what it should refuse, and refuse
a number question that no certified metric covers instead of answering with the nearest policy paragraph."""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import pytest

from nlq.refusal import check
from semantic.compiler import compile_question

AS_OF = date(2026, 9, 28)
PROBE = list(csv.DictReader(open(Path(__file__).parents[2] / "eval" / "probe" / "questions.csv")))

METRIC_OF = {
    "P09": "ptp_rate",
    "P10": "cost_per_rpc",
    "P11": "cost_per_contact",
    "P12": "paid_against_promises",
    "P13": "hardship_rate",
    "P14": "loan_delinquency_rate",
    "P15": "loan_delinquency_rate",
    "P20": "contact_attempts_per_case",
    "P22": "open_case_count",
    "P24": "open_case_count",
    "P26": "broken_promise_count",
    "P29": "average_overdue",
    "P30": "contact_count",
    "P59": "cases_on_hardship_plan",
    "P03": "roll_rate",
}


@pytest.mark.parametrize("pid,metric", sorted(METRIC_OF.items()))
def test_rephrased_metric_questions_compile_to_the_right_metric(pid, metric):
    q = next(r["question"] for r in PROBE if r["id"] == pid)
    c = compile_question(q, AS_OF)
    assert c is not None and c.metric_id == metric, q


def test_comparison_of_two_months_returns_both_periods():
    c = compile_question("Compare the cure rate of cases opened in June 2026 with May 2026.", AS_OF)
    assert "June 2026" in c.sql and "May 2026" in c.sql


def test_channel_comparison_splits_by_channel_instead_of_filtering_on_both():
    c = compile_question("How much did we spend per contact on SMS versus calls in August 2026?", AS_OF)
    assert "channel" in c.dimensions and "= 'sms'" not in c.sql


def test_agent_ranking_hides_tiny_samples():
    c = compile_question("Which agents have the highest cure rate?", AS_OF)
    assert "HAVING count(*) >= 30" in c.sql and "LIMIT 10" in c.sql


def test_delinquency_threshold_is_read_from_the_question():
    c = compile_question("What share of auto loan accounts are 30 or more days past due?", AS_OF)
    assert "dpd >= 30" in c.sql and "auto_loan" in c.sql


def test_breakdown_that_a_metric_does_not_support_is_flagged_not_dropped():
    c = compile_question("What share of customers have a delayed payroll deposit by province?", AS_OF)
    assert any("province" in x for x in c.caveats)


@pytest.mark.parametrize(
    "row",
    [r for r in PROBE if r["kind"] == "refusal" and r["id"] not in {"P34", "P36", "P41", "P50", "P52", "P53", "P54"}],
    ids=lambda r: r["id"],
)
def test_questions_that_must_be_refused_are_refused_by_the_rules(row):
    assert check(row["question"]), row["question"]


def test_a_number_question_without_a_certified_metric_is_refused():
    from nlq.pipeline import _ask

    a = _ask("What was the average handle time of calls in September?")
    assert a.refused and "no certified metric" in a.answer.lower()


def test_policy_topics_the_documents_never_cover_are_refused():
    from rag.answer import answer_question

    for q in ("Can we leave a voicemail that mentions the debt?", "What happens when a customer has passed away?"):
        assert answer_question(q)["refused"], q


def test_everyday_wording_still_finds_the_cease_contact_rule():
    from rag.answer import answer_question

    a = answer_question("What is the process when a customer asks us to stop contacting them?")
    assert not a["refused"] and a["citations"][0]["section"] == "§5.4"


def test_every_catalogue_sample_compiles_to_its_own_metric():
    """The LLM step is shown these samples; they must be recognised by the rules so the list can't drift."""
    from nlq.rewrite import CATALOGUE

    for metric_id, (_, sample) in CATALOGUE.items():
        c = compile_question(sample, AS_OF)
        assert c is not None and c.metric_id == metric_id, (metric_id, sample)


def test_forecasts_are_refused_but_the_break_risk_list_is_not():
    assert check("Forecast the cure rate for October 2026")
    assert check("Which customers will default next month?")
    assert not check("Which open promises are most likely to break this week?")


def test_llm_pick_is_thrown_away_when_it_does_not_match_the_question():
    from nlq.rewrite import grounded

    assert grounded("What proportion of people we phoned actually reached the right person?", "rpc_rate")
    assert not grounded("What was the average handle time of calls in September?", "average_dpd")
    assert not grounded("How many agents do we have on shift tomorrow?", "contact_count")


def test_without_an_llm_the_rewrite_step_does_nothing(monkeypatch):
    from common.config import get_settings
    from nlq.rewrite import choose_metric

    monkeypatch.setattr(get_settings(), "llm_provider", "offline")
    assert choose_metric("What proportion of the people we phoned actually reached the right person?") is None
