"""Human review tiers: one-by-one vs batch with a 2% sample (V1 §6 "Where a person reviews")."""

from __future__ import annotations

import math

import pytest

from tests_spec import factories as F
from tests_spec import spec_constants as C

pytestmark = pytest.mark.hitl

AT = F.weekday_local(9, 0)


def _reminder_decisions(adapter, n):
    out = []
    for i in range(n):
        case = F.case_snapshot(
            case_id=f"CASE-B-{i:04d}", customer=F.customer_contact(golden_id=f"G-B-{i:04d}"),
            open_promise=F.promise(ptp_id=f"PTP-B-{i:04d}"),
        )
        d = adapter.propose_next_best_action(case, AT)
        out.append(d)
    return out


@pytest.mark.hardship
def test_plan_offers_and_hardship_cases_are_reviewed_one_at_a_time(adapter):
    """V1 §6: "Plan offers, hardship and vulnerable cases, off-strategy actions, call summaries and
    program offers are always checked one at a time"."""
    cases = [
        F.with_customer(F.ryan_case(), hardship_flag="possible"),
        F.with_customer(F.ryan_case(case_id="CASE-V"), vulnerability_flag=True),
    ]
    for c in cases:
        d = adapter.propose_next_best_action(c, AT)
        assert d.review_mode == "individual"
    d = adapter.propose_next_best_action(F.ryan_case(case_id="CASE-P"), AT)
    if d.action.treatment in C.INDIVIDUAL_REVIEW_TREATMENTS:
        assert d.review_mode == "individual"


def test_routine_digital_reminders_may_be_batched(adapter):
    """V1 §6: "Routine digital reminders and the team-lead playbooks are approved as a batch"."""
    ds = _reminder_decisions(adapter, 10)
    digital = [d for d in ds if d.action.treatment == "reminder" and d.action.channel in ("sms", "email", "push")]
    assert all(d.review_mode == "batch" for d in digital)


@pytest.mark.parametrize("n", [1, 49, 50, 51, 120, 500])
def test_batch_sample_is_at_least_two_percent(adapter, n):
    """V1 §6: "approved as a batch, with 2% checked first" (rounding TBC: ceil, minimum 1)."""
    ds = _reminder_decisions(adapter, n)
    batchable = [d for d in ds if d.review_mode == "batch"]
    if not batchable:
        pytest.skip("no batchable decisions produced")
    b = adapter.create_approval_batch(batchable)
    need = max(math.ceil(C.BATCH_SAMPLE_FRACTION * len(b.item_ids)), C.BATCH_SAMPLE_MIN_ITEMS or 0)
    assert len(b.sample_item_ids) >= need
    assert set(b.sample_item_ids) <= set(b.item_ids)


def test_individual_items_are_kept_out_of_batches(adapter):
    """V1 §6: items that must be checked one at a time never ride along in a batch."""
    ds = _reminder_decisions(adapter, 5)
    hard = adapter.propose_next_best_action(F.with_customer(F.ryan_case(), hardship_flag="possible"), AT)
    b = adapter.create_approval_batch(ds + [hard])
    assert hard.decision_id not in b.item_ids
    assert hard.decision_id in b.excluded_item_ids


def test_batch_starts_pending(adapter):
    """V1 §6 "approved as a batch": creating a batch approves nothing by itself (Brief "Keep a human in
    the loop")."""
    ds = [d for d in _reminder_decisions(adapter, 5) if d.review_mode == "batch"]
    if not ds:
        pytest.skip("no batchable decisions produced")
    b = adapter.create_approval_batch(ds)
    assert b.status == "pending"
