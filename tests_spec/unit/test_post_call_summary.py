"""Post-call summary draft (V1 §6 UC2; v2 §6 UC2)."""

from __future__ import annotations

import datetime as dt

import pytest

from tests_spec import factories as F
from tests_spec import spec_constants as C
from tests_spec.helpers import PAN_PATTERN, word_count

pytestmark = pytest.mark.summary


def test_summary_is_at_most_80_words(adapter):
    """V1 §6 UC2: "a summary of up to 80 words"."""
    d = adapter.draft_post_call_summary(F.hardship_promise_transcript(), F.recorded_promise())
    assert 0 < word_count(d.summary) <= C.SUMMARY_MAX_WORDS


def test_draft_has_the_fixed_form_and_passes_schema_check(adapter):
    """V1 §6 UC2 "AI fills a fixed form": summary, promise (amount, date, firmness), signals (hardship,
    delay reason, dispute), next steps; v2 "the JSON must match the schema"."""
    d = adapter.draft_post_call_summary(F.hardship_promise_transcript(), F.recorded_promise())
    assert d.schema_valid
    assert {"hardship_signal", "stated_delay_reason", "dispute_signal"} <= set(d.signals)
    assert isinstance(d.next_steps, list)


def test_promise_is_extracted_with_amount_date_and_firmness(adapter):
    """V1 §6 UC2: "any promise (amount, date, and how firm it sounded)"."""
    d = adapter.draft_post_call_summary(F.hardship_promise_transcript(), F.recorded_promise())
    assert d.promise.amount == pytest.approx(400.0)
    assert d.promise.due_date == dt.date(2026, 10, 16)
    assert d.promise.intent_strength is not None and 0.0 <= d.promise.intent_strength <= 1.0


@pytest.mark.hardship
def test_hardship_cue_is_flagged_as_a_signal(adapter):
    """V1 §6 UC2: "signals such as hardship, the reason for the delay"; customer says hours cut and
    pay a month late."""
    d = adapter.draft_post_call_summary(F.hardship_promise_transcript(), F.recorded_promise())
    assert d.signals.get("hardship_signal") in ("possible", "clear")


@pytest.mark.explanation
def test_every_filled_item_links_to_its_part_of_the_call(adapter):
    """V1 §6 UC2: "Each item links to its part of the call"; v2 "every field cites the turns it came
    from (turn_index)"."""
    t = F.hardship_promise_transcript()
    d = adapter.draft_post_call_summary(t, F.recorded_promise())
    valid = {turn.turn_index for turn in t.turns}
    assert d.citations.get("promise"), "the promise must cite its turns"
    for fld, turns in d.citations.items():
        assert turns, f"{fld} has an empty citation list"
        assert set(turns) <= valid, f"{fld} cites non-existent turns {turns}"


def test_unsupported_items_stay_blank(adapter):
    """V1 §6 UC2: "unsupported items stay blank"; v2 "a field with no supporting turn is left empty"."""
    d = adapter.draft_post_call_summary(F.no_promise_transcript(), None)
    assert d.promise.amount is None and d.promise.due_date is None
    assert "promise" not in d.citations or not d.citations["promise"]
    assert d.signals.get("dispute_signal") in (None, False, "none", "")


def test_promise_that_differs_from_the_recorded_one_is_highlighted_not_fixed(adapter):
    """V1 §6 UC2: "a promise that differs from the recorded one is highlighted"; v2: "A mismatch is
    highlighted, not silently fixed"."""
    rec = F.recorded_promise(amount=250.0, due=dt.date(2026, 10, 9))
    d = adapter.draft_post_call_summary(F.hardship_promise_transcript(), rec)
    assert d.mismatches, "mismatch must be highlighted"
    assert d.promise.amount == pytest.approx(400.0), "the transcript value must not be silently replaced"


def test_matching_promise_raises_no_mismatch(adapter):
    """v2 §6 UC2: a promise amount or date must match the promises_to_pay row on that contact_id."""
    d = adapter.draft_post_call_summary(F.hardship_promise_transcript(), F.recorded_promise())
    assert not d.mismatches


@pytest.mark.hitl
def test_draft_is_not_saved_until_an_agent_approves(adapter):
    """V1 §6 UC2: "The agent edits and approves the notes, and only approved values are saved"."""
    d = adapter.draft_post_call_summary(F.hardship_promise_transcript(), F.recorded_promise())
    assert d.status == "draft"


@pytest.mark.hitl
@pytest.mark.audit
def test_agent_edits_are_saved_and_logged(adapter):
    """V1 §6 UC2 (agent edits and approves); v2 "Edits are logged, and the edit rate per field shows where
    the prompt needs work"."""
    d = adapter.draft_post_call_summary(F.hardship_promise_transcript(), F.recorded_promise())
    ok = adapter.approve_post_call_summary(d, F.person("agent", "agent-001"), edits={"next_steps": ["Send plan options"]})
    assert ok.approved_by == "agent-001"
    assert "next_steps" in ok.edited_fields
    assert ok.saved_fields.get("next_steps") == ["Send plan options"]
    assert ok.audit_id


@pytest.mark.parametrize("actor", F.NON_PERSON_ACTORS, ids=["model", "rule", "llm"])
def test_only_a_person_can_approve_a_summary(adapter, actor):
    """V1 §6 UC2 "Agent edits and approves before saving" (the approver is a person)."""
    d = adapter.draft_post_call_summary(F.hardship_promise_transcript(), F.recorded_promise())
    with pytest.raises((PermissionError, ValueError)):
        adapter.approve_post_call_summary(d, actor)


@pytest.mark.governance
def test_summary_never_contains_card_numbers(adapter):
    """V1 §6 UC2 "from the redacted transcript"; v2 "already PCI and PII redacted"."""
    t = F.transcript([
        ("agent", "Can you confirm the card?"),
        ("customer", "It's 4111 1111 1111 1111, and I can pay 100 dollars on October 20th."),
    ])
    d = adapter.draft_post_call_summary(t, None)
    blob = d.summary + " " + " ".join(d.next_steps)
    assert not PAN_PATTERN.search(blob)


def test_low_asr_confidence_marks_text_features_missing(adapter):
    """v2 §5 Coverage: calls with asr_confidence_avg below 0.80 (TBC) mark text features low-confidence;
    V1 §5 "poor recordings count as missing"."""
    thr = C.require_constant(C.ASR_CONFIDENCE_MIN, "ASR_CONFIDENCE_MIN")
    t = F.hardship_promise_transcript(asr_confidence_avg=thr - 0.2)
    d = adapter.draft_post_call_summary(t, None)
    assert d.signals.get("hardship_signal") in (None, "missing", "low_confidence") or d.signals.get("low_confidence")
