"""Novel capabilities that are rules or arithmetic: S1, S3, S6, S7, H2, H3, H5 (V1 §3, §6, §7; NI)."""

from __future__ import annotations

import datetime as dt

import pytest

from tests_spec import factories as F
from tests_spec import spec_constants as C
from tests_spec.adapter import ChannelCapacity, OpsEvent, RepaymentRecord, StressScenario


# ---------------------------------------------------------------------------
# S1 Employer shock radar
# ---------------------------------------------------------------------------
@pytest.mark.s1
def test_pay_gap_with_new_ei_looks_like_a_layoff(adapter):
    """V1 §6 Team-lead playbooks: "A pay gap with new EI looks like a layoff"; NI S1 step 4."""
    rows = adapter.employer_radar(F.employer_observations("EMP-LKS", 12, gaps=9, new_ei=7))
    r = next(x for x in rows if x.employer_key == "EMP-LKS")
    assert r.pattern == "layoff_like"
    assert r.n_payroll_gap == 9 and r.n_new_ei == 7


@pytest.mark.s1
def test_pay_gap_without_ei_looks_like_a_payroll_delay(adapter):
    """V1 §6: "without EI, more like a payroll delay"; NI S1 step 4."""
    rows = adapter.employer_radar(F.employer_observations("EMP-PAY", 12, gaps=10, new_ei=0))
    assert next(x for x in rows if x.employer_key == "EMP-PAY").pattern == "payroll_delay"


@pytest.mark.s1
def test_known_incident_is_checked_before_calling_a_pattern(adapter):
    """V1 §6: "I check ops_events first"; NI S1 step 4 "Check ops_events before calling either"."""
    ev = OpsEvent("INC-PAYROLL-1", "data_feed_issue", dt.datetime(2026, 9, 27, tzinfo=dt.UTC),
                  dt.datetime(2026, 10, 3, tzinfo=dt.UTC), "Payroll file delayed",
                  affected_tables=["deposit_accounts"])
    rows = adapter.employer_radar(F.employer_observations("EMP-PAY", 12, gaps=10, new_ei=0), [ev])
    r = next(x for x in rows if x.employer_key == "EMP-PAY")
    assert r.explained_by_incident == "INC-PAYROLL-1"


@pytest.mark.s1
def test_radar_is_not_presented_as_a_layoff_detector(adapter):
    """V1 §6: "since no field says 'laid off', I call it a radar, not a layoff detector"."""
    rows = adapter.employer_radar(F.employer_observations("EMP-LKS", 12, gaps=9, new_ei=7))
    for r in rows:
        assert "laid off" not in r.label.lower() and "layoff detected" not in r.label.lower()


@pytest.mark.s1
def test_radar_shows_open_cases_and_exposure_for_the_team_lead(adapter):
    """V1 §6: "The team lead sees the employer's open cases and exposure"; NI S1 step 5."""
    obs = F.employer_observations("EMP-LKS", 12, gaps=9, new_ei=7)
    r = next(x for x in adapter.employer_radar(obs) if x.employer_key == "EMP-LKS")
    assert r.open_cases == sum(o.has_open_case for o in obs)
    open_exposure = sum(o.exposure_cad for o in obs if o.has_open_case)
    all_exposure = sum(o.exposure_cad for o in obs)
    assert r.exposure_cad == pytest.approx(open_exposure, rel=0.01) or r.exposure_cad == pytest.approx(all_exposure, rel=0.01)


# ---------------------------------------------------------------------------
# S3 Data-health watch
# ---------------------------------------------------------------------------
@pytest.mark.s3
def test_renamed_column_is_detected_as_drift(adapter):
    """V1 §3 Data-health watch (S3): "channel in contact history was replaced by channel_v2 on 26 Sep"."""
    old = [{"contact_id": f"CT{i}", "channel": "sms", "batch_id": "B1"} for i in range(20)]
    new = [{"contact_id": f"CT{i}", "channel_v2": "sms", "batch_id": "B2"} for i in range(20)]
    rep = adapter.detect_schema_drift("contact_history", old, new)
    assert "channel_v2" in rep.added_columns and "channel" in rep.removed_columns


@pytest.mark.s3
@pytest.mark.hitl
def test_ai_drafted_fix_waits_for_an_engineer(adapter):
    """V1 §3 S3: "an AI drafts the fix and an engineer approves it"; v2 "never auto-merged"."""
    old = [{"contact_id": "CT1", "channel": "sms"}]
    new = [{"contact_id": "CT1", "channel_v2": "sms"}]
    rep = adapter.detect_schema_drift("contact_history", old, new)
    if rep.proposed_fix is not None:
        assert rep.proposed_fix.applied is False
        assert "pending" in rep.proposed_fix.status.lower()


@pytest.mark.s3
def test_null_rate_jump_is_reported(adapter):
    """V1 §3 S3: "Each load records row counts, missing values and table shapes, so I notice change"."""
    old = [{"contact_id": f"CT{i}", "outcome": "ok"} for i in range(20)]
    new = [{"contact_id": f"CT{i}", "outcome": None if i < 15 else "ok"} for i in range(20)]
    rep = adapter.detect_schema_drift("contact_history", old, new)
    assert rep.null_rate_changes.get("outcome", 0) > 0.5


# ---------------------------------------------------------------------------
# H5 Outage-victim shield
# ---------------------------------------------------------------------------
def _repayments():
    d = C.OUTAGE_START.date()
    return [
        RepaymentRecord("A-VICTIM", "G-1", d, d + dt.timedelta(days=1), fees_charged=25.0),
        RepaymentRecord("A-LATE", "G-2", d, d + dt.timedelta(days=9), fees_charged=25.0),
        RepaymentRecord("A-OTHERDAY", "G-3", dt.date(2026, 9, 2), dt.date(2026, 9, 3), fees_charged=25.0),
        RepaymentRecord("A-ONTIME", "G-4", d, d, fees_charged=0.0),
    ]


@pytest.mark.h5
def test_outage_victims_are_due_during_the_outage_and_paid_next_day(adapter):
    """V1 §3 Outage victims (H5): "accounts that were due during it and paid the next day"."""
    rep = adapter.find_outage_victims(F.outage_event(), _repayments())
    assert "A-VICTIM" in rep.candidates
    assert "A-LATE" not in rep.candidates and "A-OTHERDAY" not in rep.candidates


@pytest.mark.h5
def test_outage_list_is_a_candidate_list_compared_with_the_bank_estimate(adapter):
    """V1 §3 H5: "I compare my count with the bank's estimate ... this is a candidate list, not a final
    answer"."""
    rep = adapter.find_outage_victims(F.outage_event(), _repayments())
    assert rep.is_candidate_list is True
    assert rep.bank_estimate == C.OUTAGE_AFFECTED_EST
    assert rep.our_count == len(rep.candidates)


@pytest.mark.h5
@pytest.mark.hitl
def test_outage_refunds_and_pressure_holds_are_proposals_for_a_person(adapter):
    """V1 §6 Team-lead playbooks: "For outage victims (H5), it proposes refunding fees and pausing
    pressure"; NI H5 "for a person to approve"."""
    rep = adapter.find_outage_victims(F.outage_event(), _repayments())
    kinds = {p.kind for p in rep.proposals}
    assert {"fee_reversal", "pressure_hold"} <= kinds
    assert all(p.status == "pending_approval" for p in rep.proposals)


# ---------------------------------------------------------------------------
# S6 Capacity stress test
# ---------------------------------------------------------------------------
@pytest.mark.s6
def test_dialer_outage_moves_calls_and_leaves_the_real_plan_alone(adapter):
    """V1 §6 Stress test (S6): "what if a dialer fails ... reruns the day's plan without them to show
    which actions move"."""
    at = F.weekday_local(9, 0)
    cases = [F.case_snapshot(case_id=f"CASE-S6-{i}", days_past_due=45, customer=F.customer_contact(golden_id=f"G-S6-{i}"),
                             open_promise=None) for i in range(6)]
    decisions = [adapter.propose_next_best_action(c, at) for c in cases]
    cap = ChannelCapacity(units_by_channel={"call": 10, "sms": 10, "email": 10, "push": 10}, agent_call_slots=10)
    plan = adapter.plan_daily_queue(decisions, cap)
    before = [(d.decision_id, d.action.channel) for d in plan.scheduled]
    res = adapter.stress_test(plan, cap, StressScenario("dialer down", channel_outages=["call"]))
    assert not any(d.action.channel == "call" for d in res.plan.scheduled)
    called = {did for did, ch in before if ch == "call"}
    assert called <= {did for did, _ in res.moved}
    assert res.original_unchanged
    assert [(d.decision_id, d.action.channel) for d in plan.scheduled] == before


# ---------------------------------------------------------------------------
# S7 Early hardship signals: can only raise to possible
# ---------------------------------------------------------------------------
@pytest.mark.s7
@pytest.mark.hardship
def test_stress_signals_only_raise_hardship_to_possible(adapter):
    """NI S7: "It can only raise hardship to possible (the latch)"; V1 §10."""
    res = adapter.hardship_transition(F.hardship_state("none"), "clear", F.rule_actor("s7_stress_rule"), source="model")
    assert not res.accepted
    res2 = adapter.hardship_transition(F.hardship_state("none"), "possible", F.rule_actor("s7_stress_rule"), source="model")
    assert res2.accepted and res2.new_level == "possible"


# ---------------------------------------------------------------------------
# H2 Review board, H3 Missed offers
# ---------------------------------------------------------------------------
@pytest.mark.h2
def test_review_board_lists_due_and_overdue_vulnerability_reviews(adapter):
    """V1 §6 UC3 Review board (H2): "customers whose vulnerability review is due"; NI H2 "due or past ...
    Nothing falls off the radar silently"."""
    as_of = dt.date(2026, 10, 6)
    customers = [
        {"golden_id": "G-PAST", "vulnerability_flag": True, "vulnerability_review_date": "2026-09-01",
         "vulnerability_source": "agent", "hardship_flag": "possible", "hardship_source": "llm_flag"},
        {"golden_id": "G-TODAY", "vulnerability_flag": True, "vulnerability_review_date": "2026-10-06",
         "vulnerability_source": "customer_form", "hardship_flag": "none", "hardship_source": None},
        {"golden_id": "G-LATER", "vulnerability_flag": True, "vulnerability_review_date": "2027-01-01",
         "vulnerability_source": "agent", "hardship_flag": "none", "hardship_source": None},
    ]
    rows = adapter.review_board(customers, as_of)
    ids = {r.golden_id for r in rows}
    assert {"G-PAST", "G-TODAY"} <= ids and "G-LATER" not in ids
    past = next(r for r in rows if r.golden_id == "G-PAST")
    assert past.hardship_source == "llm_flag"


@pytest.mark.h2
@pytest.mark.fairness
def test_review_board_uses_the_flag_not_the_vulnerability_type(adapter):
    """NI H2: "Use customers.vulnerability_flag only. customers.vulnerability_type is a protected
    attribute"."""
    rows = adapter.review_board([{"golden_id": "G-1", "vulnerability_flag": True, "vulnerability_review_date": "2026-09-01",
                                  "vulnerability_type": "bereavement", "vulnerability_source": "agent",
                                  "hardship_flag": "none", "hardship_source": None}], dt.date(2026, 10, 6))
    for r in rows:
        assert "bereavement" not in repr(r)


@pytest.mark.h3
def test_missed_offers_are_hardship_cases_never_offered_a_program(adapter):
    """V1 §6 UC3 (H3): "hardship cases that were never offered a program"; NI H3 "newest first"."""
    cases = [
        {"case_id": "C-OLD", "hardship_flag": True, "hardship_program_offered": False, "case_open_date": "2026-08-01"},
        {"case_id": "C-NEW", "hardship_flag": True, "hardship_program_offered": False, "case_open_date": "2026-09-20"},
        {"case_id": "C-OFFERED", "hardship_flag": True, "hardship_program_offered": True, "case_open_date": "2026-09-21"},
        {"case_id": "C-NOHS", "hardship_flag": False, "hardship_program_offered": False, "case_open_date": "2026-09-22"},
    ]
    rep = adapter.missed_offers(cases, [])
    assert rep.missed == ["C-NEW", "C-OLD"]


@pytest.mark.h3
def test_offers_made_against_the_rules_are_shown_by_agent_and_program(adapter):
    """V1 §6 UC3 (H3): "offers made even though the rules said no (by agent and program)"; NI H3
    `eligibility_result = ineligible_overridden`."""
    offers = [
        {"offer_id": "O1", "agent_id": "agent-001", "program_id": "HP-1", "eligibility_result": "ineligible_overridden",
         "nba_recommended_flag": False, "decline_reason": None, "plan_status": "active"},
        {"offer_id": "O2", "agent_id": "agent-002", "program_id": "HP-1", "eligibility_result": "eligible",
         "nba_recommended_flag": True, "decline_reason": "still_unaffordable", "plan_status": "declined"},
    ]
    rep = adapter.missed_offers([], offers)
    ids = {o["offer_id"] for o in rep.overridden_offers}
    assert ids == {"O1"}
    o = rep.overridden_offers[0]
    assert o.get("agent_id") == "agent-001" and o.get("program_id") == "HP-1"
    assert rep.decline_reasons.get("still_unaffordable") == 1
