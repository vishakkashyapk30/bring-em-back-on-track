"""An outage (incident) affecting labels, caveats and pressure (V1 §3 H5, §4 S5, §6 UC1; NI H5)."""

from __future__ import annotations

import datetime as dt

import pytest

from tests_spec import factories as F
from tests_spec import spec_constants as C
from tests_spec.adapter import PromiseOutcome, RepaymentRecord

pytestmark = pytest.mark.h5


@pytest.fixture
def with_outage_promise(adapter):
    t = F.ryan_mitchell_tables(include_cohort=False)
    t["promises_to_pay"].append({
        "ptp_id": "PTP-OUTAGE", "case_id": "CASE-RYM-0001", "crm_customer_id": "RYM-1142", "ptp_amount": 200.0,
        "ptp_due_date": "2026-09-14", "ptp_status": "broken", "grace_days": 0,
        "ptp_created_ts": "2026-09-10 12:00:00", "paid_date": "2026-09-15",
    })
    adapter.load_sources(t)
    adapter.run_pipeline(F.AS_OF)
    return adapter


def test_outage_promise_is_not_a_break_in_training_labels(with_outage_promise):
    """V1 §6 UC1: broken promises exclude "promises due during a payment outage"; v2 Labels."""
    lbl = with_outage_promise.label_promise(
        PromiseOutcome("PTP-OUTAGE", "broken", dt.date(2026, 9, 14)), [F.outage_event()], as_of=F.AS_OF_DATE
    )
    assert lbl is None


def test_outage_promise_does_not_count_against_the_customer(with_outage_promise):
    """NI H5 "Do not chase, or charge, customers because of the bank's own outage": the outage break must
    not raise Ryan's broken-promise count above the one genuine break (PTP-0090311)."""
    gid = with_outage_promise.find_golden_id("crm", "RYM-1142")
    v = with_outage_promise.get_features_online(gid, ["ptp_broken_count_90d"]).values["ptp_broken_count_90d"]
    assert v.value == 1


@pytest.mark.s5
def test_answers_over_the_outage_period_carry_the_incident_caveat(with_outage_promise, analyst_user):
    """V1 §4 step 4 (S5) "flags incidents in the period, such as the 14 Sep app outage"."""
    ans = with_outage_promise.ask("Broken promise rate for the week of 14 September 2026", analyst_user)
    assert not ans.refused
    assert C.OUTAGE_INCIDENT_ID in ans.incidents or any("outage" in c.lower() for c in ans.caveats)


@pytest.mark.hitl
def test_outage_victim_proposals_wait_for_a_person(with_outage_promise):
    """V1 §6 playbooks: H5 "proposes refunding fees and pausing pressure"; they "wait for a team lead's
    approval"."""
    rep = with_outage_promise.find_outage_victims(
        F.outage_event(),
        [RepaymentRecord("C-88213", "G-004817", dt.date(2026, 9, 14), dt.date(2026, 9, 15), fees_charged=29.0)],
    )
    assert "C-88213" in rep.candidates
    assert rep.proposals and all(p.status == "pending_approval" for p in rep.proposals)
