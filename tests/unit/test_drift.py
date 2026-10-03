import pytest

from governance import audit, drift

OLD = [{"contact_id": f"CT{i}", "channel": "sms", "outcome": "ok"} for i in range(20)]
NEW = [{"contact_id": f"CT{i}", "channel_v2": "sms", "outcome": None if i < 15 else "ok"} for i in range(20)]


def test_rename_is_detected_with_null_rates():
    c = drift.detect("contact_history", OLD, NEW)
    assert c["added_columns"] == ["channel_v2"] and c["removed_columns"] == ["channel"]
    assert c["renames"] == [{"from": "channel", "to": "channel_v2", "complete": True}]
    assert c["null_rate_changes"]["outcome"] == 0.75


def test_type_change_is_detected():
    c = drift.detect("t", [{"amount": 1.5}], [{"amount": "1.5"}])
    assert c["type_changes"] == [{"column": "amount", "from": "number", "to": "text"}]


def test_no_change_means_no_fix():
    assert drift.draft_fix(drift.detect("t", OLD, OLD)) is None


def test_fix_is_drafted_offline_and_waits_for_an_engineer():
    fix = drift.draft_fix(drift.detect("contact_history", OLD, NEW))
    assert fix["status"] == "pending_engineer_approval" and fix["applied"] is False
    assert "channel_v2" in fix["diff"] and "not applied" in fix["diff"]
    assert fix["drafted_by"] == "rules"


def test_only_the_steward_approves_and_it_is_audited():
    fix = drift.record(drift.detect("contact_history", OLD, NEW))
    for role in ("agent", "team_lead", "analyst", "hardship_specialist"):
        with pytest.raises(PermissionError):
            drift.approve_fix(fix["fix_id"], "u", role)
    res = drift.approve_fix(fix["fix_id"], "DS-1", "data_steward")
    assert res["applied"] is False and res["audit_id"] > 0
    assert audit.query(event_type="drift_fix_approve")[0]["entity_id"] == fix["fix_id"]
    with pytest.raises(ValueError):
        drift.approve_fix(fix["fix_id"], "DS-1", "data_steward")
    assert drift.get_fix(fix["fix_id"])["applied"] is False


def test_same_change_is_stored_once():
    drift.record(drift.detect("contact_history", OLD, NEW))
    drift.record(drift.detect("contact_history", OLD, NEW))
    assert len(drift.fixes()) == 1


def test_explained_by_release_and_note():
    ev = [{"event_id": "REL-0926", "event_type": "platform_release", "affected_tables": '["contact_history"]'}]
    notes = [{"doc_id": "REL-0926", "doc_type": "release_note", "related_table": "contact_history (channel)"}]
    assert drift.detect("contact_history", OLD, NEW, ev, notes)["explanation_sources"] == ["REL-0926"]
