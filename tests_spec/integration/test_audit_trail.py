"""Every query, score, decision, edit, override and simulator run leaves an audit record (V1 §10)."""

from __future__ import annotations

import pytest

from tests_spec import factories as F
from tests_spec.adapter import PlanLevers

pytestmark = pytest.mark.audit

AT = F.weekday_local(9, 0)


def test_nba_proposal_is_audited(adapter):
    """V1 §10: the audit log records every "score, decision"; V1 §3 gold keeps append-only NBA decisions."""
    d = adapter.propose_next_best_action(F.ryan_case(), AT)
    recs = adapter.audit_log(subject_id=d.decision_id) + adapter.audit_log(subject_id=d.case_id)
    assert recs, "the proposed decision must be logged"


def test_summary_edit_and_approval_are_audited(adapter):
    """V1 §10 "every ... edit"; v2 §6 UC2 "Edits are logged"."""
    d = adapter.draft_post_call_summary(F.hardship_promise_transcript(), F.recorded_promise())
    adapter.approve_post_call_summary(d, F.person("agent", "agent-001"), edits={"next_steps": ["Call back Friday"]})
    recs = [r for r in adapter.audit_log() if r.actor_id == "agent-001"]
    assert recs
    assert any(r.details.get("edited_fields") or "edit" in r.event_type for r in recs)


def test_simulator_runs_are_audited_with_the_actor(adapter):
    """V1 §6 UC3 "Every scenario is logged"; V1 §10 "simulator run"."""
    req = F.plan_request(levers=PlanLevers(payment_reduction_pct=0.5))
    adapter.simulate_plan(req)
    recs = adapter.audit_log(event_type="simulator_run")
    assert recs and recs[-1].actor_id == req.requested_by.actor_id


def test_hardship_changes_are_audited(adapter):
    """V1 §10 + contract rule 7 (`hardship_flag_events` with reviewer and reason)."""
    adapter.hardship_transition(F.hardship_state("possible"), "none", F.person("hardship_specialist", "spec-001"),
                                reason="Evidence of full income")
    recs = [r for r in adapter.audit_log() if r.actor_id == "spec-001"]
    assert recs and any(r.reason for r in recs)


def test_refused_hardship_change_is_also_audited(adapter):
    """V1 §10 (everything is logged) + V1 §2 monitoring of overrides: an attempt a model makes to lower
    the flag is refused and leaves a trace."""
    before = len(adapter.audit_log())
    adapter.hardship_transition(F.hardship_state("possible"), "none", F.model_actor(), reason="auto")
    assert len(adapter.audit_log()) > before


def test_audit_log_is_append_only(adapter):
    """V1 §10 "An append-only audit log"; v2 "write-once in production": records only ever grow and
    earlier records are unchanged."""
    adapter.propose_next_best_action(F.ryan_case(), AT)
    first = [(r.audit_id, r.event_type, r.actor_id, r.at) for r in adapter.audit_log()]
    adapter.simulate_plan(F.plan_request(levers=PlanLevers(term_extension_months=6)))
    second = [(r.audit_id, r.event_type, r.actor_id, r.at) for r in adapter.audit_log()]
    assert second[: len(first)] == first
    assert len(second) > len(first)
