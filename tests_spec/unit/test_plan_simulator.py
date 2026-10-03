"""Hardship plan simulator: arithmetic properties (V1 §6 UC3 "Plan simulator (H1)"; NI H1)."""

from __future__ import annotations

import dataclasses
import datetime as dt

import pytest

from tests_spec import factories as F
from tests_spec import spec_constants as C
from tests_spec.adapter import PlanLevers
from tests_spec.helpers import has_label

pytestmark = [pytest.mark.hardship, pytest.mark.h1]


def sim(adapter, levers=None, **kw):
    return adapter.simulate_plan(F.plan_request(levers=levers or PlanLevers(), **kw))


def test_no_levers_reproduces_the_current_contract(adapter):
    """NI H1 "What it shows" 2: months to clear and total interest "against the current contract".
    With no lever moved the plan IS the current contract."""
    s = sim(adapter)
    assert s.new_payment == pytest.approx(s.baseline_payment)
    assert s.new_payment == pytest.approx(F.loan_terms().scheduled_payment_amount)
    assert s.months_to_clear == pytest.approx(s.baseline_months_to_clear)
    assert s.total_interest == pytest.approx(s.baseline_total_interest)


def test_payment_cut_lowers_payment_by_the_stated_share(adapter):
    """V1 §6 UC3 / NI H1 lever "Payment cut: hardship_programs.payment_reduction_pct"."""
    s = sim(adapter, PlanLevers(payment_reduction_pct=0.5))
    assert s.new_payment == pytest.approx(0.5 * s.baseline_payment, rel=0.02)


@pytest.mark.parametrize("cut_a,cut_b", [(0.1, 0.3), (0.3, 0.5)])
def test_bigger_cut_means_lower_payment_and_longer_to_clear(adapter, cut_a, cut_b):
    """NI H1 "What it shows" 1-2 (property): a deeper payment cut never raises the payment and never
    shortens the time to clear, at a positive interest rate."""
    a, b = sim(adapter, PlanLevers(payment_reduction_pct=cut_a)), sim(adapter, PlanLevers(payment_reduction_pct=cut_b))
    assert b.new_payment <= a.new_payment
    assert b.months_to_clear >= a.months_to_clear
    assert b.total_interest >= a.total_interest - 1e-6


@pytest.mark.parametrize("months", [6, 12, 24])
def test_term_extension_lowers_payment_and_costs_more_interest(adapter, months):
    """V1 §6 UC3 lever "a longer term", NI H1 `term_extension_max_months`: longer term, lower payment,
    more total interest (positive rate)."""
    base, ext = sim(adapter), sim(adapter, PlanLevers(term_extension_months=months))
    assert ext.new_payment < base.new_payment
    assert ext.months_to_clear > base.months_to_clear
    assert ext.total_interest > base.total_interest


def test_interest_freeze_never_increases_interest(adapter):
    """V1 §6 UC3 lever "an interest freeze or cut" (`rate_override`, 0% TBC)."""
    prog = F.hardship_program(rate_override=0.0)
    base, frz = sim(adapter, program=prog), sim(adapter, PlanLevers(rate_override=0.0), program=prog)
    assert frz.total_interest <= base.total_interest


def test_fee_waiver_reduces_what_the_customer_pays_by_the_fees(adapter):
    """V1 §6 UC3 lever "a fee waiver" (`fees_waived_flag`)."""
    base, waived = sim(adapter), sim(adapter, PlanLevers(fee_waiver=True))
    fees = F.loan_terms().fees_outstanding
    assert waived.total_customer_paid == pytest.approx(base.total_customer_paid - fees, abs=1.0)


def test_payment_holiday_does_not_shorten_time_to_clear(adapter):
    """V1 §6 UC3 lever "a payment holiday" (moratorium, `skip_payment`, `duration_months`)."""
    base, hol = sim(adapter), sim(adapter, PlanLevers(payment_holiday_months=2))
    assert hol.months_to_clear >= base.months_to_clear + 2 - 1e-6


def test_monthly_surplus_is_income_minus_essentials_minus_other_lenders(adapter):
    """V1 §6 UC3: the new payment is shown "against what the customer has left each month after
    essentials and other lenders"; NI H1 "What it shows" 1. Month-end so MTD == full month."""
    s = sim(adapter)
    a = F.affordability()
    expected = a.payroll_avg_amount_3m - a.essential_spend_amount_mtd - a.other_lender_payment_amount_mtd
    assert s.monthly_surplus == pytest.approx(expected, abs=1.0)
    assert s.payment_to_surplus_ratio == pytest.approx(s.new_payment / s.monthly_surplus, rel=0.01)


def test_rent_is_not_subtracted_twice(adapter):
    """V1 §6 UC3: "(rent is already part of essentials)"; NI H1 Gaps: do not subtract
    `customers.monthly_housing_cost` as well."""
    s1 = sim(adapter, affordability=F.affordability(monthly_housing_cost=0.0))
    s2 = sim(adapter, affordability=F.affordability(monthly_housing_cost=2500.0))
    assert s1.monthly_surplus == pytest.approx(s2.monthly_surplus)


def test_month_to_date_essentials_are_scaled_to_a_full_month(adapter):
    """NI H1 Gaps: `essential_spend_amount_mtd` is month-to-date, so "we scale it to a full month".
    The same MTD spend seen earlier in the month implies a higher full-month spend, so a lower surplus."""
    early = sim(adapter, affordability=F.affordability(as_of=dt.date(2026, 9, 10)))
    late = sim(adapter, affordability=F.affordability(as_of=dt.date(2026, 9, 30)))
    assert early.monthly_surplus < late.monthly_surplus


@pytest.mark.fairness
@pytest.mark.parametrize("protected", [{"household_size": 6, "dependants_count": 4}, {"household_size": 1, "dependants_count": 0}])
def test_household_size_and_dependants_never_used(adapter, protected):
    """V1 §6 UC3: "Household size and dependants are protected, so never used"; NI H1 Gaps."""
    base = sim(adapter)
    other = sim(adapter, affordability=F.affordability(protected=protected))
    assert other.monthly_surplus == pytest.approx(base.monthly_surplus)
    assert other.new_payment == pytest.approx(base.new_payment)


def test_status_quo_value_is_exposure_less_expected_loss(adapter):
    """NI H1 "What it shows" 3: "status-quo value is total_exposure less the bank's own
    expected_loss_est"."""
    s = sim(adapter)
    assert s.status_quo_value == pytest.approx(12145.0 - 3120.0, abs=0.01)
    assert s.bank_value_plan is not None


def test_missing_inputs_are_shown_as_stated_assumptions(adapter):
    """V1 §6 UC3: "Inputs missing from the data, such as discount rate and loss-given-default, are shown
    as stated assumptions"; NI H1 Gaps (TBC values)."""
    s = sim(adapter)
    keys = {k.lower() for k in s.assumptions}
    assert any("discount" in k for k in keys), keys
    assert any("loss_given_default" in k or "lgd" in k for k in keys), keys


def test_plan_hold_rate_is_labelled_observed_not_causal(adapter):
    """NI H1 "What it shows" 4: chance the plan holds is labelled "observed, not causal"; V1 §6 UC3
    "how often similar plans have held in the past"."""
    s = sim(adapter, PlanLevers(payment_reduction_pct=0.5))
    assert has_label(s.plan_hold_label, C.LABEL_OBSERVED_NOT_CAUSAL)


def test_scenario_inside_program_limits_needs_no_higher_approver(adapter):
    """V1 §6 UC3: levers "within each program's limits in hardship_programs"."""
    s = sim(adapter, PlanLevers(payment_reduction_pct=0.5, term_extension_months=12))
    assert s.within_program_rules is True


@pytest.mark.parametrize(
    "levers",
    [PlanLevers(payment_reduction_pct=0.8), PlanLevers(term_extension_months=48)],
    ids=["cut-beyond-program", "extension-beyond-program"],
)
def test_scenario_beyond_program_limits_needs_the_program_approver(adapter, levers):
    """V1 §6 UC3: "Anything beyond them needs a higher approver"; NI H1: shown as "outside program
    rules, needs hardship_programs.approver_level"."""
    prog = F.hardship_program(payment_reduction_pct=0.5, term_extension_max_months=24, approver_level="team_lead")
    s = sim(adapter, levers, program=prog)
    assert s.within_program_rules is False
    assert s.approver_level_required == "team_lead"


@pytest.mark.parametrize(
    "levers",
    [PlanLevers(term_extension_months=6), PlanLevers(payment_holiday_months=1), PlanLevers(rate_override=0.0)],
    ids=["term", "holiday", "rate"],
)
def test_cards_only_get_a_lower_payment(adapter, levers):
    """V1 §6 UC3: "Cards only get a lower payment, as the card payment formula isn't defined"."""
    prog = F.hardship_program(product_types=["card"], program_id="HP-CARD-CUT", rate_override=0.0)
    s = adapter.simulate_plan(F.plan_request(levers=levers, account=F.card_terms(), program=prog))
    assert s.rejected_levers, "non-payment-cut levers must be refused for cards"


def test_card_payment_cut_is_applied_to_minimum_payment(adapter):
    """NI H1 Gaps: "card scenarios are limited to a payment cut on minimum_payment_due"."""
    prog = F.hardship_program(product_types=["card"], program_id="HP-CARD-CUT")
    s = adapter.simulate_plan(F.plan_request(levers=PlanLevers(payment_reduction_pct=0.5), account=F.card_terms(), program=prog))
    assert not s.rejected_levers
    assert s.new_payment == pytest.approx(0.5 * F.card_terms().minimum_payment_due, rel=0.02)


def test_simulator_is_deterministic_plain_arithmetic(adapter):
    """V1 §8: "the simulator ... [is] plain rules or arithmetic, so every number can be audited"."""
    req = F.plan_request(levers=PlanLevers(payment_reduction_pct=0.3, term_extension_months=6))
    a, b = adapter.simulate_plan(req), adapter.simulate_plan(dataclasses.replace(req))
    for f in ("new_payment", "monthly_surplus", "months_to_clear", "total_interest", "bank_value_plan"):
        assert getattr(a, f) == pytest.approx(getattr(b, f)), f


@pytest.mark.audit
def test_every_scenario_is_logged(adapter):
    """V1 §6 UC3: "Every scenario is logged"; NI H1: "Each scenario viewed and the one chosen go to
    audit_log"; V1 §10 audit covers "simulator run"."""
    s = sim(adapter, PlanLevers(payment_reduction_pct=0.3))
    runs = adapter.audit_log(event_type="simulator_run")
    assert any(s.scenario_id in (r.subject_id, r.details.get("scenario_id")) for r in runs)
