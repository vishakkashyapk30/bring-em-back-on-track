"""Hardship flag latch: who or what may raise, confirm or lower it (V1 §10; v2 §9; NI H2)."""

from __future__ import annotations

import pytest

from tests_spec import factories as F
from tests_spec import spec_constants as C

pytestmark = [pytest.mark.hardship, pytest.mark.h2]

ALL_RAISERS = [
    pytest.param(F.model_actor(), "model", id="model"),
    pytest.param(F.rule_actor(), "model", id="rule"),
    pytest.param(F.llm_actor(), "llm_flag", id="llm"),
    pytest.param(F.person("agent"), "agent_coded", id="agent"),
    pytest.param(F.person("hardship_specialist"), "agent_coded", id="specialist"),
]

DOWNWARD = [("possible", "none"), ("clear", "possible"), ("clear", "none")]


# ---------------------------------------------------------------------------
# Raise
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("actor,source", ALL_RAISERS)
def test_anyone_or_anything_can_raise_to_possible(adapter, actor, source):
    """V1 §10 Hardship latch: "Any model, rule or agent can raise the flag to possible"."""
    res = adapter.hardship_transition(F.hardship_state("none"), "possible", actor, source=source)
    assert res.accepted
    assert res.new_level == "possible"


@pytest.mark.parametrize("actor", F.NON_PERSON_ACTORS, ids=["model", "rule", "llm"])
def test_models_and_rules_cannot_raise_straight_to_clear(adapter, actor):
    """NI H2: "Models and rules can only raise hardship_flag to possible"; V1 §10: a specialist
    confirms by linking a program."""
    res = adapter.hardship_transition(F.hardship_state("none"), "clear", actor, program_id="HP-PL-3M-CUT")
    assert not res.accepted
    assert res.new_level == "none"


@pytest.mark.parametrize("actor", F.NON_PERSON_ACTORS, ids=["model", "rule", "llm"])
def test_model_signal_never_downgrades_a_confirmed_flag(adapter, actor):
    """V1 §10: "Only a person can lower it". A model asking for 'possible' on a customer who is already
    'clear' must not move the flag down."""
    res = adapter.hardship_transition(F.hardship_state("clear", program_id="HP-PL-3M-CUT"), "possible", actor)
    assert not res.accepted or res.new_level == "clear"


def test_raising_is_idempotent(adapter):
    """V1 §10: raising to possible when already possible keeps the customer at possible."""
    res = adapter.hardship_transition(F.hardship_state("possible"), "possible", F.model_actor())
    assert res.new_level == "possible"


def test_raise_records_who_or_what_raised_it(adapter):
    """NI H2: `collections_cases.hardship_source` separates agent_coded, customer_form, model and
    llm_flag, "so the board can show who or what raised each flag"."""
    res = adapter.hardship_transition(F.hardship_state("none"), "possible", F.llm_actor(), source="llm_flag")
    assert res.event is not None
    assert res.event.source == "llm_flag"
    assert res.event.actor_kind == "llm"


# ---------------------------------------------------------------------------
# Confirm
# ---------------------------------------------------------------------------
def test_specialist_confirms_by_linking_a_program(adapter):
    """V1 §10: "A specialist confirms it by linking a program"."""
    res = adapter.hardship_transition(
        F.hardship_state("possible"), "clear", F.person("hardship_specialist"), reason="Income cut confirmed",
        program_id="HP-PL-3M-CUT",
    )
    assert res.accepted and res.new_level == "clear"
    assert res.event is not None and res.event.program_id == "HP-PL-3M-CUT"


def test_confirmation_without_a_program_is_refused(adapter):
    """V1 §10: confirmation is defined as linking a program; without a program it is not a confirmation."""
    res = adapter.hardship_transition(F.hardship_state("possible"), "clear", F.person("hardship_specialist"), reason="x")
    assert not res.accepted
    assert res.new_level == "possible"


def test_front_line_agent_cannot_confirm(adapter):
    """V1 §10 / v2 §9 "Confirm: a specialist confirms and links a program" -> an agent who is not a
    hardship specialist cannot confirm."""
    res = adapter.hardship_transition(
        F.hardship_state("possible"), "clear", F.person("agent"), reason="x", program_id="HP-PL-3M-CUT"
    )
    assert not res.accepted


def test_team_lead_confirmation_policy(adapter):
    """V1 §10 names only the specialist as confirmer; whether a team lead may confirm is TBC."""
    allowed = C.require_constant(C.TEAM_LEAD_MAY_CONFIRM_HARDSHIP, "TEAM_LEAD_MAY_CONFIRM_HARDSHIP")
    res = adapter.hardship_transition(
        F.hardship_state("possible"), "clear", F.person("team_lead"), reason="x", program_id="HP-PL-3M-CUT"
    )
    assert res.accepted is allowed


# ---------------------------------------------------------------------------
# Lower
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("from_level,to_level", DOWNWARD)
@pytest.mark.parametrize("actor", F.NON_PERSON_ACTORS, ids=["model", "rule", "llm"])
def test_models_rules_and_llms_never_lower_the_flag(adapter, actor, from_level, to_level):
    """V1 §10: "Only a person can lower it"; V1 §8: "Only a person can clear a hardship flag"."""
    res = adapter.hardship_transition(F.hardship_state(from_level), to_level, actor, reason="model says fine")
    assert not res.accepted
    assert res.new_level == from_level


@pytest.mark.parametrize("from_level,to_level", DOWNWARD)
@pytest.mark.parametrize("reason", [None, "", "   "])
def test_person_must_record_a_reason_to_lower(adapter, from_level, to_level, reason):
    """V1 §10: "Only a person can lower it, and they must record a reason"."""
    res = adapter.hardship_transition(F.hardship_state(from_level), to_level, F.person("hardship_specialist"), reason=reason)
    assert not res.accepted
    assert res.new_level == from_level


@pytest.mark.parametrize("from_level,to_level", DOWNWARD)
def test_person_with_reason_can_lower_and_an_event_is_written(adapter, from_level, to_level):
    """V1 §10 + contract quality rule 7: "Every change of hardship_flag down to none has a
    hardship_flag_events row with a reviewer and reason"."""
    res = adapter.hardship_transition(
        F.hardship_state(from_level), to_level, F.person("hardship_specialist", "spec-001"),
        reason="Customer back at full hours; income evidence provided",
    )
    assert res.accepted and res.new_level == to_level
    ev = res.event
    assert ev is not None
    assert ev.actor_kind == "person" and ev.actor_id == "spec-001"
    assert ev.reason and ev.reason.strip()
    assert (ev.from_level, ev.to_level) == (from_level, to_level)


def test_agent_lowering_policy(adapter):
    """V1 §10 "Only a person can lower it" does not say which roles; agent permission is TBC."""
    allowed = C.require_constant(C.AGENT_MAY_LOWER_HARDSHIP, "AGENT_MAY_LOWER_HARDSHIP")
    res = adapter.hardship_transition(F.hardship_state("possible"), "none", F.person("agent"), reason="Misheard")
    assert res.accepted is allowed


@pytest.mark.parametrize("role", ["analyst", "data_steward"])
def test_non_servicing_roles_cannot_change_the_flag(adapter, role):
    """V1 §10 Access: what people can do depends on role; analysts and stewards do not service
    customers, so they must not lower a hardship flag."""
    res = adapter.hardship_transition(F.hardship_state("possible"), "none", F.person(role), reason="cleanup")
    assert not res.accepted


@pytest.mark.parametrize("to_level", ["none", "possible", "clear"])
def test_levels_are_limited_to_the_three_states(adapter, to_level):
    """V1 §10: the flag is "none, possible or clear" (contract enum)."""
    res = adapter.hardship_transition(F.hardship_state("none"), to_level, F.person("hardship_specialist"),
                                      reason="r", program_id="HP-PL-3M-CUT")
    assert res.new_level in C.HARDSHIP_LEVELS
