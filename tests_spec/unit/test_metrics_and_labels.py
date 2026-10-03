"""Business metric and training labels (V1 §2, §6 UC1; v2 §2, §6 Labels)."""

from __future__ import annotations

import datetime as dt

import pytest

from tests_spec import factories as F
from tests_spec import spec_constants as C
from tests_spec.adapter import PromiseOutcome
from tests_spec.helpers import has_label


def _case(cure=True, days=10, insolvency=False, deceased=False, **kw):
    return {"case_id": kw.pop("case_id", "C"), "cure_flag": cure, "days_to_cure": days if cure else None,
            "insolvency_hold_flag": insolvency, "deceased_hold_flag": deceased,
            "case_open_date": "2026-09-07", **kw}


@pytest.mark.parametrize(
    "cases,expected",
    [
        ([_case(True, 10), _case(False)], 0.5),
        ([_case(True, 30), _case(True, 31)], 0.5),  # 30 counts, 31 does not
        ([_case(True, 5), _case(True, 5, insolvency=True), _case(False, deceased=True)], 1.0),  # holds excluded
        ([_case(False), _case(False)], 0.0),
    ],
    ids=["half", "boundary-30", "holds-excluded", "none-cured"],
)
def test_thirty_day_cure_rate(adapter, cases, expected):
    """V1 §2: "A case is cured when cure_flag is true and days_to_cure is 30 or less. Cases on insolvency
    or deceased hold are left out"."""
    assert adapter.cure_rate_30d(cases) == pytest.approx(expected)


def test_cure_rate_with_only_held_cases_is_undefined(adapter):
    """V1 §2: held cases are left out, so a cohort of only held cases has no rate (not 0%)."""
    assert adapter.cure_rate_30d([_case(True, 3, insolvency=True)]) is None


DUE = dt.date(2026, 9, 1)


@pytest.mark.parametrize(
    "status,expected",
    [("broken", 1), ("partially_kept", 1), ("kept", 0), ("open", None), ("cancelled", None)],
)
def test_promise_break_label(adapter, status, expected):
    """V1 §6 UC1: "a promise is broken if it was missed or part-paid after the grace period"; v2 Labels:
    broken/partially_kept = 1, kept = 0, open and cancelled excluded."""
    lbl = adapter.label_promise(PromiseOutcome("PTP-1", status, DUE, grace_days=3), [], as_of=dt.date(2026, 10, 1))
    assert lbl == expected


def test_promise_inside_grace_period_is_not_yet_labelled(adapter):
    """V1 §6 UC1: broken only "after the grace period"."""
    lbl = adapter.label_promise(PromiseOutcome("PTP-1", "broken", dt.date(2026, 9, 29), grace_days=5), [],
                                as_of=dt.date(2026, 10, 1))
    assert lbl is None


@pytest.mark.h5
def test_promises_due_during_a_payment_outage_are_excluded(adapter):
    """V1 §6 UC1: "excluding promises due during a payment outage"; v2: "promises overlapping a
    payment-posting outage in ops_events dropped"."""
    p = PromiseOutcome("PTP-OUT", "broken", C.OUTAGE_START.date(), grace_days=0)
    assert adapter.label_promise(p, [F.outage_event()], as_of=dt.date(2026, 10, 1)) is None
    p2 = PromiseOutcome("PTP-NOT", "broken", dt.date(2026, 9, 2), grace_days=0)
    assert adapter.label_promise(p2, [F.outage_event()], as_of=dt.date(2026, 10, 1)) == 1


@pytest.mark.s4
def test_scorecard_calls_a_difference_causal_only_with_random_assignment(adapter):
    """V1 §6 S4: "A difference is called causal only when cases were assigned at random"; v2 §4
    "observed, not causal"; NI S4 (`randomised_pilot`)."""
    cases = []
    for i in range(200):
        rnd = i < 100
        cases.append({
            "case_id": f"C{i}", "strategy_code": "A" if i % 2 else "B", "test_cell": ("T1" if rnd else None),
            "assignment_method": "randomised_pilot" if rnd else "rules", "entry_dpd": 31, "primary_product": "card",
            "cure_flag": i % 3 == 0, "days_to_cure": 10 if i % 3 == 0 else None, "recidivism_flag": False,
            "contact_cost_cad": 2.0, "complaint_raised_flag": False,
        })
    rows = adapter.strategy_scorecard(cases)
    assert rows
    for r in rows:
        if not r.causal:
            assert has_label(r.label, C.LABEL_OBSERVED_NOT_CAUSAL)
    obs_only = adapter.strategy_scorecard([c for c in cases if c["assignment_method"] != "randomised_pilot"])
    assert all(not r.causal for r in obs_only)


@pytest.mark.s4
def test_scorecard_splits_by_entry_dpd_and_product(adapter):
    """V1 §6 S4: compares strategies "by delinquency stage and product"; NI S4 "split by entry DPD and
    product so mix shifts don't mislead"."""
    cases = [{"case_id": f"C{i}", "strategy_code": "A", "test_cell": None, "assignment_method": "rules",
              "entry_dpd": 31 if i % 2 else 61, "primary_product": "card" if i % 3 else "personal_loan",
              "cure_flag": True, "days_to_cure": 5, "recidivism_flag": False, "contact_cost_cad": 1.0,
              "complaint_raised_flag": False} for i in range(60)]
    rows = adapter.strategy_scorecard(cases)
    segs = {tuple(sorted(r.segment.items())) for r in rows}
    assert len(segs) >= 2
