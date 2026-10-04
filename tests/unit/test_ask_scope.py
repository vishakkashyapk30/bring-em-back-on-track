"""Authorisation for Ask is decided before anything runs and is the same in rules and language-model mode."""

import pytest

from common import ask_scope, llm_mode
from common.config import get_settings
from nlq import pipeline


def _no_sql(*_a, **_k):
    raise AssertionError("SQL must not run for a role that may not receive a metric")


def test_agent_metric_question_is_refused_before_any_sql_runs(monkeypatch):
    import nlq.executor as ex

    monkeypatch.setattr(ex, "execute", _no_sql)
    with ask_scope.use_scope(ask_scope.AskScope(allow_metrics=False)):
        a = pipeline.ask("How many collections cases are open today, by current bucket?")
    assert a.refused and "analysts and team leads" in a.answer


@pytest.mark.parametrize("mode", ["rules", "llm"])
def test_language_model_is_never_asked_when_the_role_may_not_receive_a_metric(monkeypatch, mode):
    monkeypatch.setattr(get_settings(), "llm_provider", "ollama")
    called = []
    import llm.client as client

    monkeypatch.setattr(client, "complete_json", lambda *a, **k: called.append(a) or {})
    with ask_scope.use_scope(ask_scope.AskScope(allow_metrics=False)), llm_mode.use_mode(mode):
        a = pipeline.ask("What proportion of the people we phoned in September actually reached the right person?")
    assert a.refused and not called


def test_call_summary_of_a_case_the_role_does_not_own_is_refused(monkeypatch):
    import decisioning.post_call as pc

    monkeypatch.setattr(pc, "summarise", lambda **_k: (_ for _ in ()).throw(AssertionError("must not read the call")))
    scope = ask_scope.AskScope(allow_metrics=False, case_allowed=lambda c: False,
                               case_denied_reason="Refused: not yours.")
    with ask_scope.use_scope(scope):
        a = pipeline.ask("Summarise the most recent recorded call on case CS-2026-000001: what did the customer say?")
    assert a.refused and a.answer == "Refused: not yours."


def test_policy_questions_stay_open_to_a_role_without_metrics():
    with ask_scope.use_scope(ask_scope.AskScope(allow_metrics=False)):
        a = pipeline.ask("Does the National Do Not Call List stop collection calls?")
    assert not a.refused and a.kind == "policy"


def test_an_agent_can_list_their_own_cases_and_only_theirs(monkeypatch):
    seen = {}
    import nlq.executor as ex

    def fake(sql, *a, **k):
        seen["sql"] = sql
        return sql, ["case_id"], [("CS-1",)]

    monkeypatch.setattr(ex, "execute", fake)
    scope = ask_scope.AskScope(allow_metrics=False, user_id="AG-7", role="agent")
    with ask_scope.use_scope(scope):
        a = pipeline.ask("Show my open cases with a broken promise")
    assert a.kind == "cases" and not a.refused and a.rows == [["CS-1"]]
    assert "c.assigned_agent_id = 'AG-7'" in seen["sql"] and "promises_broken > 0" in seen["sql"]


def test_the_own_cases_listing_is_not_available_to_other_roles(monkeypatch):
    import nlq.executor as ex

    monkeypatch.setattr(ex, "execute", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not run")))
    with ask_scope.use_scope(ask_scope.AskScope(allow_metrics=True, user_id="AN-1", role="analyst")):
        a = pipeline.ask("Show my open cases with a broken promise")
    assert a.kind != "cases"


def test_how_many_promises_to_pay_were_broken_is_a_certified_metric():
    from datetime import date

    from semantic.compiler import compile_question

    c = compile_question("How many promises to pay were broken between 10 Sep and 20 Sep 2026?", date(2026, 9, 28))
    assert c is not None and c.metric_id == "broken_promise_count"
