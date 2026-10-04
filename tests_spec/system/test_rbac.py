"""Role-based access: who can see or do what (V1 §10 Access; v2 §1 Users, §4, §9; V1 §6 review table).

The permission matrix below is derived from the docs. ``None`` = the docs do not say (TBC) and the
case skips. See open_questions.md.
"""

from __future__ import annotations

import pytest

from tests_spec import spec_constants as C
from tests_spec.adapter import Action, PlanLevers
from tests_spec.helpers import assert_denied

pytestmark = pytest.mark.rbac

ROLES = ["agent", "hardship_specialist", "team_lead", "analyst", "data_steward"]

# capability -> role -> allowed?   (source in the comment)
MATRIX: dict[str, dict[str, bool | None]] = {
    # V1 §6 table: "Agent approves or overrides". Settled by the build team, see docs/profiling/profiling_decisions.md:
    # a hardship specialist may approve; a team lead approves batches only, not single items.
    "approve_own_nba": {"agent": True, "hardship_specialist": True, "team_lead": False, "analyst": False, "data_steward": False},
    # V1 §6 table: "team lead approves batches"
    "approve_batch": {"agent": False, "hardship_specialist": False, "team_lead": True, "analyst": False, "data_steward": False},
    # V1 §3 pass 3: "a data steward decides"
    "decide_identity_review": {"agent": False, "hardship_specialist": False, "team_lead": False, "analyst": False, "data_steward": True},
    # V1 §6 UC3: "A specialist can try ...". Settled by the build team: only the specialist runs the simulator.
    "simulate_plan": {"agent": False, "hardship_specialist": True, "team_lead": False, "analyst": False, "data_steward": False},
    # V1 §10 latch: a specialist confirms by linking a program
    "confirm_hardship": {"agent": False, "hardship_specialist": True, "team_lead": C.TEAM_LEAD_MAY_CONFIRM_HARDSHIP, "analyst": False, "data_steward": False},
    # V1 §3 S3: "an engineer approves it" (steward = Collections Data Engineering lead, V1 Part 3)
    "approve_drift_fix": {"agent": False, "hardship_specialist": False, "team_lead": False, "analyst": False, "data_steward": True},
    # V1 §6 playbooks "wait for a team lead's approval". Settled by the build team: team lead only.
    "approve_playbook": {"agent": False, "hardship_specialist": False, "team_lead": True, "analyst": False, "data_steward": False},
}


def _cell(cap, role):
    v = MATRIX[cap][role]
    if v is None:
        pytest.skip(f"{cap} for {role} is not settled in the docs (TBC)")
    return v


def _attempt(login, cap, role, ryan_item, ryan_gid):
    s = login(role)
    if cap == "approve_own_nba":
        return lambda: s.approve_action(ryan_item.decision_id)
    if cap == "approve_batch":
        lead_batches = login("team_lead").list_batches()
        if not lead_batches:
            pytest.skip("no batch to approve")
        bid = lead_batches[0].batch_id
        login("team_lead").mark_sample_reviewed(bid)
        return lambda: s.approve_batch(bid)
    if cap == "decide_identity_review":
        q = login("data_steward").identity_review_queue()
        if not q:
            pytest.skip("identity review queue empty")
        return lambda: s.decide_identity_review(q[0].item_id, link=False, reason="different people")
    if cap == "simulate_plan":
        return lambda: s.simulate_plan("CASE-RYM-0001", "HP-CARD-CUT", PlanLevers(payment_reduction_pct=0.5))
    if cap == "confirm_hardship":
        return lambda: s.set_hardship_flag(ryan_gid, "clear", reason="income cut confirmed", program_id="HP-CARD-CUT")
    if cap == "approve_drift_fix":
        fixes = login("data_steward").drift_fixes()
        if not fixes:
            pytest.skip("no drift fix pending")
        return lambda: s.approve_drift_fix(fixes[0].fix_id)
    if cap == "approve_playbook":
        props = login("team_lead").playbook_proposals()
        if not props:
            pytest.skip("no playbook proposal pending")
        return lambda: s.approve_proposal(props[0].proposal_id)
    raise AssertionError(cap)


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("cap", sorted(MATRIX))
def test_permission_matrix(login, ryan_item, ryan_gid, cap, role):
    """V1 §10 Access: "What people see depends on their role: agent, hardship specialist, team lead,
    analyst or data steward"; per-capability sources are in MATRIX comments."""
    allowed = _cell(cap, role)
    fn = _attempt(login, cap, role, ryan_item, ryan_gid)
    if allowed:
        try:
            res = fn()
        except PermissionError as exc:  # pragma: no cover - reported as failure
            pytest.fail(f"{role} should be allowed to {cap}: {exc}")
        assert getattr(res, "allowed", True), f"{role} should be allowed to {cap}: {res!r}"
    else:
        assert_denied(fn)


def test_agent_sees_only_own_cases(login):
    """v2 §4: "Agents see their own cases (assigned_agent_id), team leads their team"."""
    q1 = login("agent").work_queue()
    assert q1 and all((i.assigned_agent_id in (None, "agent-001")) for i in q1)
    q2 = login("agent_other").work_queue()
    assert not any(i.case_id == "CASE-RYM-0001" for i in q2)


def test_agent_cannot_open_another_agents_customer(login, ryan_gid):
    """v2 §4 row filters + V1 §10 Access."""
    assert_denied(login("agent_other").open_customer, ryan_gid)


def test_agent_cannot_act_on_another_agents_decision(login, ryan_item):
    """V1 §10 Access + V1 §6 "Agent approves or overrides" (their own case)."""
    assert_denied(login("agent_other").approve_action, ryan_item.decision_id)


def test_analyst_sees_masked_identity_or_nothing(login, ryan_gid):
    """V1 Part 3 schema: display_name "masked for analysts"; phone/email tokenised; v2 §4 analysts see
    aggregates."""
    s = login("analyst")
    try:
        view = s.open_customer(ryan_gid)
    except PermissionError:
        return
    assert view is None or "display_name" in view.masked_fields or "Ryan" not in str(view.fields.get("display_name", ""))
    if view is not None:
        assert "+15195550142" not in repr(view.fields)


@pytest.mark.fairness
@pytest.mark.parametrize("role", ROLES)
def test_no_role_sees_protected_attributes_on_the_customer_screen(login, ryan_gid, role):
    """V1 §10: protected attributes are used only in "A restricted view ... to check outcomes and errors
    by group", never on servicing screens."""
    s = login(role)
    try:
        view = s.open_customer(ryan_gid)
    except PermissionError:
        return
    if view is None:
        return
    assert not set(view.fields) & set(C.ALL_EXCLUDED_FROM_DECISIONS)


@pytest.mark.parametrize("role", ROLES)
def test_nobody_can_delete_audit_records(login, role):
    """V1 §10 "append-only audit log"; v2 "write-once in production"."""
    s = login(role)
    recs = login("team_lead").audit_log()
    if not recs:
        pytest.skip("no audit records yet")
    assert_denied(s.delete_audit_record, recs[0].audit_id)


def test_override_requires_a_reason(login, ryan_item):
    """V1 §6 "anything can be overridden" + v2 §6 "override and edit reasons feed monitoring"."""
    assert_denied(login("agent").override_action, ryan_item.decision_id, Action("no_contact"), "")


@pytest.mark.parametrize("role", ["analyst", "data_steward"])
def test_non_servicing_roles_cannot_lower_hardship(login, ryan_gid, role):
    """V1 §10 latch ("Only a person can lower it") read with V1 §10 Access: analysts and stewards do not
    service customers."""
    assert_denied(login(role).set_hardship_flag, ryan_gid, "none", reason="tidy up")
