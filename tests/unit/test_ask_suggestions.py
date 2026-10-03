"""Every suggested question must work for the persona it is shown to (no warehouse needed)."""

from datetime import date

from api.services.ask_suggestions import ANALYST, POLICY, TEAM_LEAD, for_role
from nlq.refusal import check
from rag.answer import answer_question
from semantic.compiler import compile_question

AS_OF = date(2026, 9, 28)


def _is_policy(q: str) -> bool:
    return not answer_question(q)["refused"]


def test_agent_suggestions_are_policy_questions_the_documents_answer():
    for q in POLICY:
        assert not check(q) and _is_policy(q), q


def test_team_lead_suggestions_compile_to_a_metric_or_are_policy():
    for q in TEAM_LEAD:
        assert not check(q), q
        assert compile_question(q, AS_OF) is not None or _is_policy(q), q


def test_analyst_suggestions_compile_except_the_one_meant_to_be_refused():
    for q in ANALYST[:-1]:
        assert not check(q) and compile_question(q, AS_OF) is not None, q
    assert check(ANALYST[-1])


def test_personas_without_ask_get_an_explanation_not_a_list():
    assert for_role("steward")["questions"] == [] and for_role("hardship_specialist")["questions"] == []
