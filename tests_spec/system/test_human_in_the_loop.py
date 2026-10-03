"""Human-in-the-loop guarantees: nothing reaches a customer without approval (Brief ground rules
"Keep a human in the loop"; Brief Part 1 Rules "A human can review anything that affects a customer";
V1 §6 "Where a person reviews")."""

from __future__ import annotations

import datetime as dt

import pytest

from tests_spec import factories as F
from tests_spec.adapter import Action, PlanLevers
from tests_spec.helpers import assert_allowed, assert_denied

pytestmark = pytest.mark.hitl

LATER = F.AS_OF + dt.timedelta(hours=6)


def test_nightly_run_alone_sends_nothing(seeded):
    """Brief "nothing that affects a customer happens without a person able to review it": after the
    nightly run the queue is proposed, not sent."""
    assert seeded.outbound_messages() == []
    assert seeded.dispatch_due(LATER) == []


def test_every_outbound_message_traces_to_a_person_approval(seeded, login, ryan_item):
    """V1 §6: "Agent approves or overrides; team lead approves batches" -> anything sent carries an
    approver."""
    login("agent").approve_action(ryan_item.decision_id)
    lead = login("team_lead")
    for b in lead.list_batches():
        lead.mark_sample_reviewed(b.batch_id)
        lead.approve_batch(b.batch_id)
    seeded.dispatch_due(LATER)
    for m in seeded.outbound_messages():
        assert m.approved_by, f"message {m.message_id} left without a person's approval"


def test_batch_cannot_be_approved_before_the_sample_is_checked(login):
    """V1 §6: "approved as a batch, with 2% checked first"."""
    lead = login("team_lead")
    batches = lead.list_batches()
    if not batches:
        pytest.skip("no batch produced")
    assert_denied(lead.approve_batch, batches[0].batch_id)


def test_any_batch_item_can_be_stopped(seeded, login):
    """v2 §6: "2% sampled before send, any item can be stopped"; V1 §6 "anything can be overridden"."""
    lead = login("team_lead")
    batches = lead.list_batches()
    if not batches:
        pytest.skip("no batch produced")
    b = batches[0]
    lead.mark_sample_reviewed(b.batch_id)
    stopped = b.item_ids[0]
    assert_allowed(lead.stop_batch_item(b.batch_id, stopped, reason="Customer called in this morning"))
    lead.approve_batch(b.batch_id)
    seeded.dispatch_due(LATER)
    assert not any(m.decision_id == stopped for m in seeded.outbound_messages())


def test_override_is_logged_with_reason_and_replaces_the_proposal(seeded, login, ryan_item):
    """V1 §6 "anything can be overridden"; V1 §10 audit records every override; v2 "override and edit
    reasons feed monitoring"."""
    agent = login("agent")
    res = agent.override_action(ryan_item.decision_id, Action("specialist_referral", "call"), reason="Asked for a specialist")
    assert_allowed(res)
    recs = agent.audit_log(subject_id=ryan_item.decision_id)
    ov = [r for r in recs if "override" in r.event_type]
    assert ov and ov[-1].reason == "Asked for a specialist"


def test_override_rate_is_monitored_with_a_25_percent_trigger(seeded, login):
    """V1 §2: "how often agents override the system. Anything above 25% gets a review"; V1 §10 monitoring."""
    agent = login("agent")
    items = agent.work_queue()
    if len(items) < 2:
        pytest.skip("need at least two decisions")
    for it in items:
        agent.override_action(it.decision_id, Action("no_contact"), reason="test override")
    mon = login("team_lead").monitoring()
    assert mon.override_rate is not None and mon.override_rate > 0.25
    assert mon.override_review_triggered


def test_guardrail_counters_are_zero_after_a_normal_day(seeded, login, ryan_item):
    """V1 §2: "Three things stay at zero: pressure on customers in hardship, breaches of contact limits,
    and calls outside permitted hours"."""
    login("agent").approve_action(ryan_item.decision_id)
    seeded.dispatch_due(LATER)
    mon = login("team_lead").monitoring()
    assert mon.pressure_on_hardship_count == 0
    assert mon.contact_cap_breach_count == 0
    assert mon.out_of_hours_contact_count == 0


@pytest.mark.summary
def test_post_call_summary_saved_only_after_agent_approval(login):
    """V1 §6 UC2: "The agent edits and approves the notes, and only approved values are saved"."""
    agent = login("agent")
    draft = agent.post_call_summary("CT-RYM-0090")
    assert draft.status == "draft"
    assert_allowed(agent.approve_post_call_summary(draft.draft_id, edits={"next_steps": ["Send plan options"]}))
    recs = agent.audit_log(subject_id=draft.draft_id)
    assert recs


@pytest.mark.h1
@pytest.mark.hardship
def test_plan_beyond_program_limits_waits_for_the_program_approver(seeded, login):
    """V1 §6 UC3: "Anything beyond them needs a higher approver"; "approver_level signs off above their
    level"; NI H1 "nothing reaches the customer from the simulator"."""
    spec = login("hardship_specialist")
    sc = spec.simulate_plan("CASE-RYM-0001", "HP-CARD-CUT", PlanLevers(payment_reduction_pct=0.9))
    assert sc.within_program_rules is False
    sub = spec.submit_plan_offer(sc.scenario_id)
    assert sub.status in ("pending_approval", "refused")
    seeded.dispatch_due(LATER)
    assert not any(m.golden_id == "G-004817" and m.decision_id == sub.record_id for m in seeded.outbound_messages())


@pytest.mark.h1
def test_simulator_alone_never_contacts_the_customer(seeded, login):
    """NI H1 Human review: "nothing reaches the customer from the simulator"."""
    spec = login("hardship_specialist")
    for cut in (0.2, 0.5):
        spec.simulate_plan("CASE-RYM-0001", "HP-CARD-CUT", PlanLevers(payment_reduction_pct=cut))
    seeded.dispatch_due(LATER)
    assert seeded.outbound_messages() == []


@pytest.mark.s1
def test_contacting_customers_not_yet_behind_needs_policy_office_signoff(login):
    """V1 §6 playbooks: "Contacting customers not yet behind needs Policy Office sign-off"; contract Not
    allowed; NI S1 Scope."""
    for p in login("team_lead").playbook_proposals():
        if p.kind == "contact":
            assert p.requires_policy_office_signoff, p


@pytest.mark.identity
def test_identity_review_waits_for_the_steward(login):
    """V1 §3 pass 3: "An AI reads a masked pair; a data steward decides"."""
    q = login("data_steward").identity_review_queue()
    for item in q:
        assert item.decided is False
