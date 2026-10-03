"""Approved post-call hardship cue -> hardship flag -> pressure removed from NBA
(V1 §5 "Only values an agent has approved reach the online store"; V1 §6 UC2; V1 §10 latch)."""

from __future__ import annotations

import pytest

from tests_spec import factories as F
from tests_spec.helpers import is_pressure

pytestmark = [pytest.mark.hardship, pytest.mark.summary, pytest.mark.h2]

AT = F.weekday_local(10, 0)


@pytest.fixture
def no_hardship_yet(adapter):
    """Ryan without any hardship evidence on file (flag none), so the summary is what raises it."""
    t = F.ryan_mitchell_tables(include_cohort=False)
    t["collections_cases"][0]["hardship_mentioned_flag"] = False
    t["call_transcripts"] = []
    adapter.load_sources(t)
    adapter.run_pipeline(F.AS_OF)
    gid = adapter.find_golden_id("crm", "RYM-1142")
    assert adapter.get_golden_record(gid).hardship_flag == "none", "precondition: no hardship evidence yet"
    return adapter, gid


def _transcript(gid):
    return F.hardship_promise_transcript(golden_id=gid)


def test_unapproved_draft_changes_nothing(no_hardship_yet):
    """V1 §6 UC2 "only approved values are saved"; V1 §5 "Only values an agent has approved reach the
    online store"."""
    adapter, gid = no_hardship_yet
    adapter.draft_post_call_summary(_transcript(gid), F.recorded_promise())
    assert adapter.get_hardship_state(gid).level == "none"
    vec = adapter.get_features_online(gid, ["hardship_signal"])
    v = vec.values.get("hardship_signal")
    assert v is None or not v.present or v.value in (None, "none")


def test_approved_hardship_cue_raises_flag_and_removes_pressure(no_hardship_yet):
    """V1 §10: "Any model, rule or agent can raise the flag to possible, and pressure stops straight
    away"; V1 §6 step 1 routes to a trained agent; V1 §9 re-score after "a new hardship flag"."""
    adapter, gid = no_hardship_yet
    draft = adapter.draft_post_call_summary(_transcript(gid), F.recorded_promise())
    assert draft.signals.get("hardship_signal") in ("possible", "clear")
    adapter.approve_post_call_summary(draft, F.person("agent", "agent-001"))
    assert adapter.get_hardship_state(gid).level in ("possible", "clear")
    d = adapter.propose_next_best_action_for_case("CASE-RYM-0001", AT)
    assert not is_pressure(d.action)
    assert d.route_to


def test_agent_who_deletes_the_cue_keeps_the_flag_down(no_hardship_yet):
    """V1 §6 UC2: "The agent edits and approves the notes, and only approved values are saved"."""
    adapter, gid = no_hardship_yet
    draft = adapter.draft_post_call_summary(_transcript(gid), F.recorded_promise())
    adapter.approve_post_call_summary(draft, F.person("agent", "agent-001"), edits={"hardship_signal": "none"})
    assert adapter.get_hardship_state(gid).level == "none"


def test_approved_signal_reaches_the_online_store_with_its_prompt_version(no_hardship_yet):
    """V1 §5: AI features "are stored with the prompt version that produced them"; only approved values
    reach the online store."""
    adapter, gid = no_hardship_yet
    draft = adapter.draft_post_call_summary(_transcript(gid), F.recorded_promise())
    adapter.approve_post_call_summary(draft, F.person("agent", "agent-001"))
    v = adapter.get_features_online(gid, ["hardship_signal"]).values["hardship_signal"]
    assert v.present and v.value in ("possible", "clear")
    assert v.version


@pytest.mark.audit
def test_flag_change_is_logged_with_its_source(no_hardship_yet):
    """V1 §10 audit log ("every ... decision, edit"); NI H2 hardship_source shows "who or what raised each
    flag"."""
    adapter, gid = no_hardship_yet
    draft = adapter.draft_post_call_summary(_transcript(gid), F.recorded_promise())
    adapter.approve_post_call_summary(draft, F.person("agent", "agent-001"))
    recs = adapter.audit_log(subject_id=gid)
    assert any("hardship" in r.event_type for r in recs), [r.event_type for r in recs]


def test_later_model_signal_cannot_lower_the_flag_raised_by_the_summary(no_hardship_yet):
    """V1 §10: "Only a person can lower it"."""
    adapter, gid = no_hardship_yet
    draft = adapter.draft_post_call_summary(_transcript(gid), F.recorded_promise())
    adapter.approve_post_call_summary(draft, F.person("agent", "agent-001"))
    state = adapter.get_hardship_state(gid)
    res = adapter.hardship_transition(state, "none", F.model_actor(), reason="score dropped")
    assert not res.accepted
    assert adapter.get_hardship_state(gid).level == state.level
