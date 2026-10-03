"""Next Best Action: treatment ladder, model rules, Phase 2 gate, explanations (V1 §6 UC1)."""

from __future__ import annotations

import dataclasses
import datetime as dt

import pytest

from tests_spec import factories as F
from tests_spec import spec_constants as C
from tests_spec.adapter import ChannelCapacity, ModelEval, PayrollInfo, PromiseDraft
from tests_spec.helpers import decision_signature, has_label, is_pressure

pytestmark = pytest.mark.nba

AT = F.weekday_local(9, 0)


# ---------------------------------------------------------------------------
# Action shape
# ---------------------------------------------------------------------------
def test_action_has_treatment_channel_and_window_from_the_allowed_sets(adapter):
    """V1 §6 UC1: an action is (what to do, channel, time window); treatments reminder / payment link /
    plan offer / referral / nothing; channels call, text, email, app, letter; windows morning, afternoon,
    evening, any time."""
    d = adapter.propose_next_best_action(F.ryan_case(), AT)
    assert d.action.treatment in C.TREATMENTS
    if d.action.treatment != "no_contact":
        assert d.action.channel in C.CHANNELS
        assert d.action.window in C.TIME_WINDOWS


# ---------------------------------------------------------------------------
# Treatment ladder (plain rules)
# ---------------------------------------------------------------------------
def test_low_risk_promise_gets_no_contact(adapter):
    """V1 §6 UC1 Phase 1 step 3: "A low-risk promise gets no contact"."""
    a = adapter.apply_treatment_ladder(F.case_snapshot(), C.CLEARLY_LOW_RISK)
    assert a.treatment == "no_contact"


@pytest.mark.parametrize("days", [0, 1, C.REMINDER_DUE_WITHIN_DAYS])
def test_high_risk_promise_due_soon_gets_a_reminder(adapter, days):
    """V1 §6 UC1 Phase 1 step 3: "A high-risk one due within three days gets a reminder"."""
    case = F.case_snapshot(open_promise=F.promise(due_date=F.AS_OF_DATE + dt.timedelta(days=days)))
    a = adapter.apply_treatment_ladder(case, C.CLEARLY_HIGH_RISK)
    assert a.treatment == "reminder"


def test_broken_promise_with_late_pay_gets_a_plan_offer(adapter):
    """V1 §6 UC1 Phase 1 step 3: "A broken promise from someone whose pay is late gets a plan offer"
    (v2: `payroll_delay_days > 0`)."""
    case = F.case_snapshot(
        open_promise=None,
        last_broken_promise=F.promise(status="broken", due_date=F.AS_OF_DATE - dt.timedelta(days=5)),
        payroll_delay_days=12,
    )
    a = adapter.apply_treatment_ladder(case, C.CLEARLY_HIGH_RISK)
    assert a.treatment == "plan_offer"


def test_over_30_dpd_and_high_risk_gets_an_agent_call(adapter):
    """V1 §6 UC1 Phase 1 step 3: "Cases more than 30 days behind and at high risk get a call from an
    agent" (v2: "31+ DPD and high risk: agent call")."""
    case = F.case_snapshot(days_past_due=C.AGENT_CALL_MIN_DPD + 10, open_promise=None, payroll_delay_days=0)
    a = adapter.apply_treatment_ladder(case, C.CLEARLY_HIGH_RISK)
    assert a.channel == "call"


def test_ladder_is_plain_rules_and_deterministic(adapter):
    """V1 §8 "Where I deliberately avoid AI: ... the ladder ... plain rules"."""
    case = F.ryan_case()
    assert adapter.apply_treatment_ladder(case, 0.8) == adapter.apply_treatment_ladder(dataclasses.replace(case), 0.8)


# ---------------------------------------------------------------------------
# Policy gate comes first
# ---------------------------------------------------------------------------
@pytest.mark.policy_gate
@pytest.mark.parametrize("block", ["cease", "insolvency", "deceased"])
def test_nba_never_contacts_a_blocked_customer_however_risky(adapter, block):
    """V1 §6 UC1 Phase 1 step 1: "Policy rules come first. Before any model runs, plain rules remove what
    I must not do"."""
    case = F.with_customer(F.ryan_case(), contact_block=block)
    d = adapter.propose_next_best_action(case, AT)
    assert d.action.treatment == "no_contact"


@pytest.mark.hardship
@pytest.mark.parametrize("flag", ["possible", "clear"])
def test_nba_never_proposes_pressure_to_a_customer_in_hardship(adapter, flag):
    """V1 §6 step 1 "A hardship ... flag removes pressure actions"; V1 §2 guardrail "pressure on customers
    in hardship" stays at zero."""
    d = adapter.propose_next_best_action(F.with_customer(F.ryan_case(), hardship_flag=flag), AT)
    assert not is_pressure(d.action)
    assert d.route_to


@pytest.mark.policy_gate
def test_nba_respects_the_weekly_cap_and_explains_it(adapter):
    """V1 §6 step 1 weekly contact limit + step 5 example "No call: 3 of 3 contacts used this week"."""
    case = F.with_customer(F.ryan_case(), contacts_last_7d=3, contact_cap_7d=3)
    d = adapter.propose_next_best_action(case, AT)
    assert d.action.channel != "call" or d.action.treatment == "no_contact"
    assert any("3 of 3" in r for r in d.explanation.rules_applied), d.explanation.rules_applied


# ---------------------------------------------------------------------------
# Explanation format (fixed template, no AI)
# ---------------------------------------------------------------------------
@pytest.mark.explanation
def test_every_decision_has_a_three_part_explanation(adapter):
    """V1 §6 step 5: "Every suggestion explains itself in a fixed format ...: which rules applied, the main
    reasons behind the risk score, and what has changed"; Brief "Explain every decision"."""
    d = adapter.propose_next_best_action(F.ryan_case(), AT)
    e = d.explanation
    assert isinstance(e.rules_applied, list) and isinstance(e.risk_reasons, list) and isinstance(e.changes, list)
    assert e.text.strip()
    assert e.risk_reasons, "the main reasons behind the risk score must be shown"


@pytest.mark.explanation
def test_explanation_is_written_without_ai(adapter):
    """V1 §6 step 5 "written without AI"; v2 "from reason codes in a fixed template, no LLM"; V1 §8."""
    d = adapter.propose_next_best_action(F.ryan_case(), AT)
    assert d.explanation.generated_by.lower() == "template"


@pytest.mark.explanation
def test_explanation_is_reproducible(adapter):
    """V1 §6 step 5 fixed format: the same case yields the same words."""
    a = adapter.propose_next_best_action(F.ryan_case(), AT)
    b = adapter.propose_next_best_action(F.ryan_case(), AT)
    assert a.explanation.text == b.explanation.text


@pytest.mark.explanation
def test_payroll_delay_appears_as_a_plain_reason(adapter):
    """V1 §6 step 5 example reason: "Payroll 29 days late" (Ryan, NI §8 step 2)."""
    d = adapter.propose_next_best_action(F.ryan_case(), AT)
    assert any("29" in r and "payroll" in r.lower() for r in d.explanation.risk_reasons), d.explanation.risk_reasons


@pytest.mark.explanation
def test_what_changed_mentions_the_broken_promise(adapter):
    """v2 §6 explanation "what changed ('Promise PTP-0090311 broken')"."""
    d = adapter.propose_next_best_action(F.ryan_case(), AT)
    assert any("PTP-0090311" in c for c in d.explanation.changes), d.explanation.changes


@pytest.mark.explanation
def test_no_contact_decisions_are_explained_too(adapter):
    """Brief ground rules "Explain every decision": also when the decision is to do nothing."""
    d = adapter.propose_next_best_action(F.with_customer(F.ryan_case(), contact_block="cease"), AT)
    assert d.explanation.text.strip() and d.explanation.rules_applied


# ---------------------------------------------------------------------------
# Fairness
# ---------------------------------------------------------------------------
@pytest.mark.fairness
@pytest.mark.parametrize("attr,a,b", F.single_attribute_variants())
def test_protected_attributes_never_change_the_decision(adapter, attr, a, b):
    """Brief Part 1 Rules "No protected attributes in decisions"; V1 §10: none of the 12 (plus age, age
    band) feed a model or a rule."""
    ca = F.with_customer(F.ryan_case(), protected={attr: a})
    cb = F.with_customer(F.ryan_case(), protected={attr: b})
    assert decision_signature(adapter.propose_next_best_action(ca, AT)) == decision_signature(
        adapter.propose_next_best_action(cb, AT)
    )


@pytest.mark.fairness
def test_risk_score_ignores_protected_features_passed_in(adapter):
    """V1 §10 Protected attributes: none feed a model."""
    base = dict(F.ryan_case().features)
    sa = adapter.score_break_risk({**base, **F.PROTECTED_VARIANT_A})
    sb = adapter.score_break_risk({**base, **F.PROTECTED_VARIANT_B})
    assert sa == pytest.approx(sb)


@pytest.mark.fairness
def test_vulnerability_flag_can_only_make_treatment_gentler(adapter):
    """V1 §10: "I do use vulnerability_flag, because it can only make treatment gentler"."""
    plain = adapter.propose_next_best_action(F.ryan_case(), AT)
    vuln = adapter.propose_next_best_action(F.with_customer(F.ryan_case(), vulnerability_flag=True), AT)
    assert not is_pressure(vuln.action)
    if not is_pressure(plain.action):
        assert vuln.action.treatment in C.NON_PRESSURE_TREATMENTS


# ---------------------------------------------------------------------------
# Promise-break model rules
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("feature", C.MONOTONE_INCREASING_FEATURES)
def test_more_late_payments_never_lower_the_risk(adapter, feature):
    """V1 §6 step 2: "It is constrained so that more late payments never lower the risk" (v2 monotone
    constraints)."""
    base = dict(F.ryan_case().features)
    scores = [adapter.score_break_risk({**base, feature: v}) for v in (0, 1, 2, 5, 10, 40, 90)]
    assert all(b >= a - 1e-9 for a, b in zip(scores, scores[1:])), scores


def test_risk_is_a_probability(adapter):
    """V1 §6 step 2: "predicts how likely each promise is to be broken"."""
    p = adapter.score_break_risk(F.ryan_case().features)
    assert 0.0 <= p <= 1.0


@pytest.mark.parametrize("challenger_auc,expected", [(0.70, C.INCUMBENT_MODEL), (0.74, C.INCUMBENT_MODEL), (0.79, "challenger")])
def test_keep_the_incumbent_unless_the_challenger_beats_it(adapter, challenger_auc, expected):
    """V1 §6 step 2: "If it doesn't beat the bank's v2.1, I keep v2.1"; V1 §2 (ptp_break v2.1, AUC 0.74,
    same later set of promises)."""
    chosen = adapter.choose_break_model(
        ModelEval("challenger", challenger_auc, "oot-2026-07-09"), ModelEval(C.INCUMBENT_MODEL, C.INCUMBENT_AUC, "oot-2026-07-09")
    )
    assert chosen == expected


def test_models_compared_on_different_sets_are_not_compared(adapter):
    """V1 §2: compare "on the same later set of promises"; a challenger evaluated on another set must
    not replace the incumbent."""
    chosen = adapter.choose_break_model(
        ModelEval("challenger", 0.90, "in-sample"), ModelEval(C.INCUMBENT_MODEL, C.INCUMBENT_AUC, "oot-2026-07-09")
    )
    assert chosen == C.INCUMBENT_MODEL


# ---------------------------------------------------------------------------
# Phase 2 uplift gate
# ---------------------------------------------------------------------------
ALL_OK = {t: 5000 for t in C.TREATMENTS}


@pytest.mark.parametrize(
    "overlap,counts,enabled",
    [
        (0.80, ALL_OK, True),
        (0.70, ALL_OK, True),
        (0.69, ALL_OK, False),
        (0.95, {**ALL_OK, "plan_offer": 999}, False),
        (0.95, {**ALL_OK, "plan_offer": 1000}, True),
        (0.10, {t: 10 for t in C.TREATMENTS}, False),
    ],
)
def test_uplift_runs_only_when_checks_pass(adapter, overlap, counts, enabled):
    """V1 §6 Phase 2: "if under 70% of open cases have comparable history, or any action has under 1,000
    cases, I keep the rules and report that uplift can't be measured yet"."""
    g = adapter.uplift_readiness(overlap, counts)
    assert g.enabled is enabled
    if not enabled:
        assert g.reason


# ---------------------------------------------------------------------------
# Capacity and expected value
# ---------------------------------------------------------------------------
def test_daily_plan_fills_capacity_by_expected_value(adapter):
    """V1 §6 step 3: "Actions fill the day's channel capacity and agent shifts by expected value: break
    chance times amount at risk, minus contact cost"."""
    cases = [
        F.case_snapshot(case_id=f"CASE-EV-{i}", amount_at_risk_cad=amt, customer=F.customer_contact(golden_id=f"G-EV-{i}"),
                        open_promise=F.promise(ptp_id=f"PTP-EV-{i}", due_date=F.AS_OF_DATE + dt.timedelta(days=1)))
        for i, amt in enumerate([100.0, 9000.0, 2500.0, 50.0])
    ]
    decisions = [adapter.propose_next_best_action(c, AT) for c in cases]
    contacting = [d for d in decisions if d.action.treatment != "no_contact" and d.action.channel]
    if len(contacting) < 2:
        pytest.skip("fewer than two contacting decisions to rank")
    ch = contacting[0].action.channel
    same = [d for d in contacting if d.action.channel == ch]
    plan = adapter.plan_daily_queue(same, ChannelCapacity(units_by_channel={ch: 1}, agent_call_slots=1))
    assert len(plan.scheduled) <= 1
    if plan.scheduled:
        top = max(same, key=lambda d: d.expected_value or 0)
        assert plan.scheduled[0].decision_id == top.decision_id
        assert {d.decision_id for d in plan.deferred} == {d.decision_id for d in same} - {top.decision_id}


def test_expected_value_formula(adapter):
    """V1 §6 step 3: expected value = break chance x amount at risk - contact cost."""
    case = F.ryan_case()
    d = adapter.propose_next_best_action(case, AT)
    if d.action.treatment == "no_contact" or d.break_probability is None or d.expected_value is None:
        pytest.skip("decision has no contact expected value")
    expected = d.break_probability * case.amount_at_risk_cad - case.contact_cost_cad
    assert d.expected_value == pytest.approx(expected, rel=0.05, abs=0.5)


# ---------------------------------------------------------------------------
# A1: payday-anchored windows, day level
# ---------------------------------------------------------------------------
@pytest.mark.a1
def test_windows_are_only_the_capacity_time_bands(adapter):
    """NI A1: "channel_capacity.time_band offers only 08-12, 12-17, 17-21 and all_day, so planned windows
    follow those bands" (V1 §6: morning, afternoon, evening, any time)."""
    for case in F.random_population(seed=3, n=20):
        d = adapter.propose_next_best_action(case, AT)
        if d.action.treatment != "no_contact":
            assert d.action.window in C.TIME_WINDOWS


@pytest.mark.a1
def test_payday_timing_is_by_day_not_hour(adapter):
    """V1 §6 step 3: "Payday timing is by day, as deposits have dates but no times"; NI A1 DF 2 at hour
    level. A reminder anchored to payday must not claim an hour-precise slot after the deposit."""
    d = adapter.propose_next_best_action(F.ryan_case(), AT)
    text = (d.explanation.text + " ".join(d.explanation.risk_reasons)).lower()
    assert "hours after" not in text and "hours since payroll" not in text


# ---------------------------------------------------------------------------
# A2: promise vs payday check
# ---------------------------------------------------------------------------
@pytest.mark.a2
def test_promise_check_counts_days_before_payday(adapter):
    """V1 §6 step 4: "the agent sees how many days it falls before payday"; NI A2 "this date is N days
    before your stated payday"."""
    chk = adapter.check_promise(
        PromiseDraft("CASE-RYM-0001", 400.0, dt.date(2026, 10, 9)),
        PayrollInfo(expected_next_payroll_date=dt.date(2026, 10, 15), customer_stated_income_date=dt.date(2026, 10, 15)),
        F.ryan_case(),
    )
    assert chk.days_before_payday == 6


@pytest.mark.a2
def test_promise_what_if_is_labelled_a_model_estimate(adapter):
    """V1 §6 step 4: "The risk updates live, labelled a model estimate, not cause and effect"; NI A2
    "model-implied"."""
    chk = adapter.check_promise(
        PromiseDraft("CASE-RYM-0001", 400.0, dt.date(2026, 10, 16)),
        PayrollInfo(expected_next_payroll_date=dt.date(2026, 10, 15)),
        F.ryan_case(),
    )
    assert chk.break_probability is not None and 0 <= chk.break_probability <= 1
    assert has_label(chk.label, C.LABEL_MODEL_ESTIMATE, C.LABEL_MODEL_IMPLIED)


@pytest.mark.a2
def test_promise_what_if_saves_nothing(adapter):
    """V1 §6 step 4 "can try another date": trying a date is a what-if, not a recorded promise
    (Brief "Keep a human in the loop")."""
    chk = adapter.check_promise(
        PromiseDraft("CASE-RYM-0001", 200.0, dt.date(2026, 10, 20)),
        PayrollInfo(expected_next_payroll_date=dt.date(2026, 10, 15)),
        F.ryan_case(),
    )
    assert chk.saved is False
