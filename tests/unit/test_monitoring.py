"""governance.monitoring: the counting rules (also run by the spec suite) and the read-only snapshot."""

from governance import monitoring as m


def test_override_rate_counts_only_a_persons_own_change_and_triggers_above_25_percent():
    recs = [{"approved_via": "agent", "proposed": "a", "final": None},
            {"approved_via": "agent", "proposed": "a", "final": "b"},
            {"approved_via": "batch", "proposed": "a", "final": None},
            {"approved_via": None, "proposed": "a", "final": "b"}]
    assert m.override_rate(recs) == (1 / 3, 3, 1)
    snap = m.snapshot(decisions=recs, sent=[], refusals=0, with_warehouse=False)
    assert snap["override_review_triggered"] and snap["override_review_threshold"] == 0.25
    assert m.override_rate([])[0] is None


def test_guardrail_counters():
    ok = {"treatment": "plan_offer", "channel": "call", "hardship_flag": "clear", "contacts_last_7d": 0,
          "contact_cap_7d": 3}
    bad = {"treatment": "reminder", "channel": "sms", "hardship_flag": "possible", "contacts_last_7d": 3,
           "contact_cap_7d": 3}
    assert m.guardrail_counts([ok], lambda r: False) == {
        "pressure_on_hardship_count": 0, "contact_cap_breach_count": 0, "out_of_hours_contact_count": 0}
    g = m.guardrail_counts([ok, bad], lambda r: True)
    assert g == {"pressure_on_hardship_count": 1, "contact_cap_breach_count": 1, "out_of_hours_contact_count": 1}


def test_snapshot_is_read_only_and_reports_psi_as_not_computed(monkeypatch):
    monkeypatch.setattr(m, "ops_decisions", lambda: [])
    monkeypatch.setattr(m, "_refusals", lambda: 2)
    monkeypatch.setattr(m, "_pressure_on_flagged", lambda d: 0)
    s = m.snapshot(with_warehouse=False)
    assert s["refusal_count"] == 2 and s["psi"] is None and s["guardrails_ok"] and s["override_rate"] is None
