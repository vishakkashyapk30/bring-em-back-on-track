"""The demo storyline, end to end (NI §8 "Demo storyline (Ryan Mitchell, updated)")."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from tests_spec import factories as F
from tests_spec import spec_constants as C
from tests_spec.adapter import PlanLevers
from tests_spec.helpers import assert_allowed, has_label, is_pressure

pytestmark = pytest.mark.demo


def test_step1_the_trap_no_work_hour_pressure_calls(seeded, login, ryan_item):
    """NI §8 step 1 "The trap. Ryan is 38 DPD on a card; the legacy rules keep calling him in work hours".
    The new system's proposal for him is not a pressure call, and any call sits inside his permitted
    hours (V1 §6 step 1)."""
    a = ryan_item.action
    assert not is_pressure(a)
    if a.channel == "call" and a.scheduled_at:
        local = a.scheduled_at.astimezone(ZoneInfo(F.TORONTO))
        assert 8 <= local.hour < 20 and local.weekday() != 6


def test_step2_one_view_links_his_records_and_shows_the_late_pay(login, ryan_gid):
    """NI §8 step 2 "One view. C360 links his records. His payroll is 29 days late"; Brief C360 mock-up
    (4 source IDs -> 1 golden ID, match confidence, lineage over the sources)."""
    view = login("agent").open_customer(ryan_gid)
    ids = " ".join(view.source_ids)
    for sid in ("C-88213", "L-5538921", "RYM-1142", "CHQ-7730"):
        assert sid in ids
    assert view.match_confidence is not None and 0 < view.match_confidence <= 1
    assert view.fields.get("payroll_delay_days") == 29
    assert view.badges.get("hardship") in ("possible", "clear")
    assert view.lineage


@pytest.mark.s1
def test_step2_employer_radar_shows_colleagues_late_with_new_ei(login):
    """NI §8 step 2 "the employer radar shows his employer's other customers are late too, with new EI
    deposits (S1)" (only shown if profiling confirms an employer effect)."""
    rows = login("team_lead").employer_radar()
    # employer_key is tokenised (V1 Part 3), so find the cohort by size: Ryan + 12 colleagues = 13.
    assert any(r.n_customers >= 13 and r.pattern == "layoff_like" for r in rows), rows


@pytest.mark.a2
def test_step3_promise_before_payday_is_flagged_and_moved(login):
    """NI §8 step 3 "The agent sees the promised date falls before his stated payday and moves it (A2)";
    V1 §6 step 4 label."""
    agent = login("agent")
    chk = agent.check_promise("CASE-RYM-0001", 400.0, dt.date(2026, 10, 9))
    assert chk.days_before_payday == 6
    assert has_label(chk.label, C.LABEL_MODEL_ESTIMATE, C.LABEL_MODEL_IMPLIED)
    moved = agent.check_promise("CASE-RYM-0001", 400.0, dt.date(2026, 10, 16))
    assert moved.days_before_payday is not None and moved.days_before_payday <= 0
    res = agent.record_promise("CASE-RYM-0001", 400.0, dt.date(2026, 10, 16))
    assert_allowed(res)


@pytest.mark.h1
@pytest.mark.hardship
def test_step4_specialist_tries_a_cut_then_an_extension(login, ryan_gid):
    """NI §8 step 4 "The hardship specialist opens the simulator, tries a 3-month cut, then a term
    extension, and sees affordability against bank cost (H1). The latch has already stopped pressure"."""
    spec = login("hardship_specialist")
    elig = spec.eligibility(ryan_gid)
    assert elig and all(e.decided_by.lower() == "rules" for e in elig)
    cut = spec.simulate_plan("CASE-RYM-0001", "HP-CARD-CUT", PlanLevers(payment_reduction_pct=0.5))
    assert cut.new_payment < cut.baseline_payment
    assert cut.monthly_surplus is not None and cut.bank_value_plan is not None and cut.status_quo_value is not None
    assert has_label(cut.plan_hold_label, C.LABEL_OBSERVED_NOT_CAUSAL)
    # NI §8 then tries a term extension, but Ryan's delinquent product is a card and V1 §6 UC3 says
    # "Cards only get a lower payment". V1 is primary, so the extension lever must be refused for the
    # card (open_questions.md Q6).
    ext = spec.simulate_plan("CASE-RYM-0001", "HP-CARD-CUT", PlanLevers(term_extension_months=6))
    assert ext.rejected_levers
    queue_actions = [i.action for i in login("agent").work_queue() if i.golden_id == ryan_gid]
    assert not any(is_pressure(a) for a in queue_actions)


@pytest.mark.s1
@pytest.mark.hitl
def test_step5_team_lead_approves_one_batch_after_checking_the_sample(login):
    """NI §8 step 5 "The team lead sees the same employer cluster on the map and approves one batch for
    the other open cases there"; V1 §6 "approved as a batch, with 2% checked first"."""
    lead = login("team_lead")
    batches = lead.list_batches()
    if not batches:
        pytest.skip("no batch produced for the cohort")
    b = batches[0]
    assert b.sample_item_ids
    assert_allowed(lead.mark_sample_reviewed(b.batch_id))
    res = lead.approve_batch(b.batch_id)
    assert_allowed(res)
    recs = lead.audit_log(subject_id=b.batch_id)
    assert any(r.actor_id == "lead-001" for r in recs)


@pytest.mark.audit
def test_storyline_leaves_a_complete_audit_trail(login, ryan_gid, ryan_item):
    """V1 §10: "An append-only audit log records every query, score, decision, edit, override and
    simulator run"; V1 §6 "Everything is logged"."""
    agent = login("agent")
    agent.open_customer(ryan_gid)
    agent.approve_action(ryan_item.decision_id, note="Agreed with customer")
    login("hardship_specialist").simulate_plan("CASE-RYM-0001", "HP-CARD-CUT", PlanLevers(payment_reduction_pct=0.5))
    login("analyst").ask("Which customers are most likely to break a promise to pay this week?")
    types = {r.event_type for r in login("team_lead").audit_log()}
    for needed in ("decision", "simulator_run", "query"):
        assert any(needed in t for t in types), (needed, types)
