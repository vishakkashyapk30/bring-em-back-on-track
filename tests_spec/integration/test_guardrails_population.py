"""Guardrails held across a mixed population: policy gate -> NBA (V1 §2 'What must not get worse';
V1 §6 UC1 Phase 1 step 1)."""

from __future__ import annotations

import dataclasses

import pytest

from tests_spec import factories as F
from tests_spec.helpers import contacts_customer, decision_signature, is_pressure

pytestmark = [pytest.mark.policy_gate, pytest.mark.nba]

AT = F.weekday_local(11, 0)
POPULATION = F.random_population(seed=2026, n=60)


@pytest.mark.parametrize("case", POPULATION, ids=[c.case_id for c in POPULATION])
def test_no_guardrail_is_breached(adapter, case):
    """V1 §2: "Three things stay at zero: pressure on customers in hardship, breaches of contact limits,
    and calls outside permitted hours"; plus blocks, disputes, representatives and consent (V1 §6 step 1).
    Every NBA proposal must also be one the policy gate permits."""
    d = adapter.propose_next_best_action(case, AT)
    c = case.customer
    a = d.action
    if c.contact_block in ("cease", "insolvency", "deceased") or c.dispute_open_flag:
        assert not contacts_customer(a)
    if c.contact_block == "represented":
        assert not contacts_customer(a) or d.route_to
    if c.hardship_flag != "none" or c.vulnerability_flag:
        assert not is_pressure(a)
    if contacts_customer(a) and a.channel in ("call", "sms", "email", "push"):
        assert c.consent.get(a.channel) is True, "unconsented channel proposed"
    if contacts_customer(a) and a.channel == "call" and c.contacts_last_7d >= c.contact_cap_7d:
        pytest.fail("call proposed although the weekly cap is used up")
    if contacts_customer(a):
        when = a.scheduled_at or AT
        gate = adapter.policy_gate(c, [dataclasses.replace(a, scheduled_at=when)], when)
        assert gate.is_permitted(a), f"NBA proposed an action the gate blocks: {gate.blocked}"
    assert d.explanation.text.strip()


@pytest.mark.fairness
@pytest.mark.parametrize("case", POPULATION[:20], ids=[c.case_id for c in POPULATION[:20]])
def test_swapping_all_protected_attributes_changes_nothing(adapter, case):
    """Brief "No protected attributes in decisions" as a population property: swapping every protected
    attribute at once never changes the decision."""
    a = F.with_customer(case, protected=dict(F.PROTECTED_VARIANT_A))
    b = F.with_customer(case, protected=dict(F.PROTECTED_VARIANT_B))
    assert decision_signature(adapter.propose_next_best_action(a, AT)) == decision_signature(
        adapter.propose_next_best_action(b, AT)
    )
