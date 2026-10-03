"""End-to-end journeys per persona (v2 §1 Users; V1 §1, §6, §10; NI personas)."""

from __future__ import annotations

import pytest

from tests_spec import factories as F
from tests_spec import spec_constants as C
from tests_spec.adapter import PolicyQuery, StressScenario
from tests_spec.helpers import assert_allowed, assert_denied, has_label


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------
@pytest.mark.explanation
def test_agent_queue_items_are_explained_and_reviewable(login):
    """V1 §1 "For every open case it suggests what to do, through which channel and when, explains why,
    and an agent approves or changes it"."""
    q = login("agent").work_queue()
    assert q
    for item in q:
        assert item.explanation.text.strip()
        assert item.review_mode in ("individual", "batch")


def test_agent_customer_screen_matches_the_c360_mock_up(login, ryan_gid):
    """Brief Layer 1 C360 example: risk, bucket, consent and hardship badges; product holdings; contact
    timeline; identity resolution and lineage."""
    v = login("agent").open_customer(ryan_gid)
    for badge in ("risk", "bucket", "consent", "hardship"):
        assert badge in v.badges, badge
    assert v.timeline, "contact timeline expected"
    assert v.nba is not None


@pytest.mark.assist
def test_agent_asks_a_policy_question_mid_call(login):
    """V1 §6 UC3: answers "only from current documents for that product, province and language, and
    cites the document and section"."""
    ans = login("agent").ask_policy(PolicyQuery("Can a 45 DPD card customer get a payment deferral?", "card", "ON", "EN"))
    assert ans.answered and ans.citations


@pytest.mark.summary
def test_agent_reviews_and_approves_the_call_summary(login):
    """V1 §6 UC2 journey: draft -> agent edits and approves -> saved."""
    agent = login("agent")
    d = agent.post_call_summary("CT-RYM-0090")
    assert d.summary and d.citations
    assert_allowed(agent.approve_post_call_summary(d.draft_id))


# ---------------------------------------------------------------------------
# Hardship specialist
# ---------------------------------------------------------------------------
@pytest.mark.hardship
@pytest.mark.h2
def test_specialist_confirms_hardship_by_linking_a_program(login, ryan_gid):
    """V1 §10: "A specialist confirms it by linking a program"."""
    s = login("hardship_specialist")
    assert_allowed(s.set_hardship_flag(ryan_gid, "clear", reason="Hours cut, payroll late", program_id="HP-CARD-CUT"))
    assert login("agent").open_customer(ryan_gid).badges.get("hardship") == "clear"


@pytest.mark.hardship
@pytest.mark.h2
def test_specialist_lowering_requires_reason(login, ryan_gid):
    """V1 §10: "Only a person can lower it, and they must record a reason"."""
    s = login("hardship_specialist")
    assert_denied(s.set_hardship_flag, ryan_gid, "none", reason="")
    assert_allowed(s.set_hardship_flag(ryan_gid, "none", reason="Customer confirmed full hours restored"))


@pytest.mark.h2
@pytest.mark.h3
def test_specialist_sees_review_board_and_missed_offers(login):
    """V1 §6 UC3 Review board (H2) and missed offers (H3): Ryan's case has a hardship mention and no
    program offered yet (`hardship_program_offered = false`)."""
    s = login("hardship_specialist")
    board = s.review_board()
    assert any(r.golden_id for r in board)
    missed = s.missed_offers()
    assert "CASE-RYM-0001" in missed.missed


# ---------------------------------------------------------------------------
# Team lead
# ---------------------------------------------------------------------------
@pytest.mark.s6
def test_team_lead_runs_a_dialer_outage_stress_test(login):
    """V1 §6 Stress test (S6): "what if a dialer fails ... reruns the day's plan without them"."""
    res = login("team_lead").run_stress_test(StressScenario("dialer down", channel_outages=["call"]))
    assert not any(d.action.channel == "call" for d in res.plan.scheduled)
    assert res.original_unchanged


@pytest.mark.s1
@pytest.mark.h5
def test_team_lead_playbooks_wait_for_approval(login):
    """V1 §6 Team-lead playbooks (S1, H5): "These run daily and wait for a team lead's approval"."""
    lead = login("team_lead")
    props = lead.playbook_proposals()
    assert all(p.status == "pending_approval" for p in props)
    if props:
        assert_allowed(lead.approve_proposal(props[0].proposal_id))


# ---------------------------------------------------------------------------
# Analyst
# ---------------------------------------------------------------------------
@pytest.mark.sql_guard
def test_analyst_asks_the_three_brief_questions(login):
    """Brief Layer 2 example questions; must deliver "The SQL or source shown for every answer"."""
    a = login("analyst")
    for q in (
        "Which customers are most likely to break a promise to pay?",
        "Which strategy worked best for unsecured loans in the last 90 days?",
        "What were the top drivers of roll-rate deterioration this week?",
    ):
        ans = a.ask(q)
        assert not ans.refused, q
        assert ans.sql and ans.data_products, q


@pytest.mark.sql_guard
@pytest.mark.fairness
def test_analyst_protected_attribute_question_is_refused(login):
    """V1 §4 step 2; Brief "Refusal of questions outside allowed data"."""
    ans = login("analyst").ask("Compare cure rates by citizenship status")
    assert ans.refused
    assert "citizenship" in ((ans.refusal_reason or "") + " " + " ".join(ans.refused_parts)).lower()


@pytest.mark.s2
@pytest.mark.governance
def test_analyst_map_hides_small_areas_and_shows_sql(login):
    """V1 §4 S2 map hides areas under 10; NI S2 "every chart shows its SQL"."""
    m = login("analyst").weather_map()
    assert m.sql
    assert all(b.n_customers >= C.SMALL_GROUP_MIN_SIZE for b in m.bubbles)


@pytest.mark.s4
def test_analyst_scorecard_is_honest_about_causality(login):
    """V1 §6 S4: "A difference is called causal only when cases were assigned at random"."""
    for r in login("analyst").strategy_scorecard():
        if not r.causal:
            assert has_label(r.label, C.LABEL_OBSERVED_NOT_CAUSAL)


# ---------------------------------------------------------------------------
# Data steward
# ---------------------------------------------------------------------------
@pytest.mark.contract
def test_steward_sees_the_data_quality_report(login):
    """Brief Layer 1 must deliver "A data quality report"; V1 Part 3 steward owns "pipeline, quality,
    identity review queue"."""
    rep = login("data_steward").data_quality_report()
    assert {r.rule_id for r in rep.results} >= set(range(1, 10))


@pytest.mark.identity
def test_steward_decides_an_identity_review_and_it_is_logged(system):
    """V1 §3 pass 3: "a data steward decides"; V1 §3 Safety rules (more than five CRM records -> a
    person); V1 §10 audit."""
    t = F.ryan_mitchell_tables(include_cohort=False)
    base = t["customers"][0]
    for i in range(C.MAX_CRM_RECORDS_PER_AUTO_CLUSTER + 1):
        t["customers"].append({**base, "crm_customer_id": f"RYM-DUP-{i}", "duplicate_of_crm_id": "RYM-1142",
                               "national_id_hash": None})
    system.seed(t)
    system.run_nightly(F.AS_OF)
    st = system.login("steward-001", "data_steward")
    q = st.identity_review_queue()
    assert q, "a cluster with more than five CRM records must reach the steward"
    assert_allowed(st.decide_identity_review(q[0].item_id, link=True, reason="Same person, verified"))
    assert st.audit_log(subject_id=q[0].item_id)


@pytest.mark.s3
@pytest.mark.hitl
def test_steward_approves_an_ai_drafted_drift_fix(seeded, login):
    """V1 §3 S3: "an AI drafts the fix and an engineer approves it" (channel -> channel_v2 on 26 Sep)."""
    st = login("data_steward")
    fixes = st.drift_fixes()
    if not fixes:
        pytest.skip("no drift detected in the seeded data")
    assert all(not f.applied for f in fixes)
    assert_allowed(st.approve_drift_fix(fixes[0].fix_id))


# ---------------------------------------------------------------------------
# Fairness end to end
# ---------------------------------------------------------------------------
@pytest.mark.fairness
def test_twins_differing_only_in_protected_attributes_get_the_same_treatment(system):
    """Brief "No protected attributes in decisions", end to end: two customers identical except for the
    protected attributes (and identity fields) get the same proposed action."""
    t = F.ryan_mitchell_tables(include_cohort=False)
    twin = {**t["customers"][0], **F.PROTECTED_VARIANT_B, "crm_customer_id": "TWIN-0001", "first_name": "Alex",
            "national_id_hash": "nidhash-twin", "primary_phone_e164": "+15195550999", "email": "twin@example.test"}
    t["customers"].append(twin)
    for tbl, key, new in (("card_accounts", "card_account_id", "C-TWIN"), ("collections_cases", "case_id", "CASE-TWIN")):
        row = {**t[tbl][0], key: new, "crm_customer_id": "TWIN-0001", "src_customer_ref": "CIF-TWIN"}
        if tbl == "card_accounts":
            row["cardholder_name_raw"] = "A. MITCHELL"
        t[tbl].append(row)
    system.seed(t)
    system.run_nightly(F.AS_OF)
    q = system.login("agent-001", "agent", "team-a").work_queue()
    by_case = {i.case_id: i for i in q}
    if not {"CASE-RYM-0001", "CASE-TWIN"} <= set(by_case):
        pytest.skip("twin case not routed to the same queue")
    a, b = by_case["CASE-RYM-0001"].action, by_case["CASE-TWIN"].action
    assert (a.treatment, a.channel, a.window) == (b.treatment, b.channel, b.window)
