# ruff: noqa: E501
"""Layer 4 invariants: the gate runs on plain rules, hardship removes pressure, the allocator respects capacity."""

from datetime import datetime
from zoneinfo import ZoneInfo

from decisioning import allocator
from decisioning.policy_gate import gate, holidays
from decisioning.schemas import Action

TZ = ZoneInfo("America/Toronto")
TUE_NOON = datetime(2026, 9, 29, 12, 0, tzinfo=TZ)
CANDS = [
    Action(treatment=t, channel=c)
    for t, c in [
        ("reminder", "push"),
        ("reminder", "sms"),
        ("payment_link", "sms"),
        ("plan_offer", "call"),
        ("specialist_referral", "call"),
    ]
]


def cust(**kw):
    base = {
        "time_zone": "America/Toronto",
        "consent": {"call": True, "sms": True, "email": True, "push": True},
        "permitted_call_start_local": "08:00",
        "permitted_call_end_local": "20:00",
        "sunday_contact_permitted": False,
        "internal_do_not_call_flag": False,
        "contact_block": "none",
        "third_party_rep_flag": False,
        "dispute_open_flag": False,
        "hardship_flag": "none",
        "vulnerability_flag": False,
        "contacts_last_7d": 0,
        "contact_cap_7d": 3,
    }
    return base | kw


def allowed(res):
    return {(a.treatment.value, a.channel.value if a.channel else None) for a in res.allowed}


def test_clean_customer_gets_everything():
    assert allowed(gate(cust(), CANDS, TUE_NOON)) == {
        ("reminder", "push"),
        ("reminder", "sms"),
        ("payment_link", "sms"),
        ("plan_offer", "call"),
        ("specialist_referral", "call"),
    }


def test_missing_consent_means_no_consent():
    res = gate(cust(consent={"call": None, "sms": False, "email": True, "push": True}), CANDS, TUE_NOON)
    assert allowed(res) == {("reminder", "push")}


def test_contact_cap_blocks_every_channel_with_a_reason():
    res = gate(cust(contacts_last_7d=3), CANDS, TUE_NOON)
    assert not res.allowed
    assert any(
        "3 of 3" in (res.reason_for(b.treatment.value, b.channel.value if b.channel else None) or "")
        for b in res.blocked
    )


def test_calls_outside_hours_blocked_but_sms_ok():
    late = datetime(2026, 9, 29, 21, 30, tzinfo=TZ)
    res = gate(cust(), CANDS, late)
    assert ("plan_offer", "call") not in allowed(res) and ("payment_link", "sms") in allowed(res)


def test_no_calls_on_sunday_even_with_the_customer_flag():
    """V1 says never Sundays; the per-customer flag only matters if Compliance flips the switch."""
    sunday = datetime(2026, 9, 27, 12, 0, tzinfo=TZ)
    assert ("plan_offer", "call") not in allowed(gate(cust(), CANDS, sunday))
    assert ("plan_offer", "call") not in allowed(gate(cust(sunday_contact_permitted=True), CANDS, sunday))


def test_sunday_flag_unlocks_calls_only_when_the_switch_is_on(monkeypatch):
    from decisioning import policy_gate

    monkeypatch.setattr(policy_gate, "SUNDAY_FLAG_UNLOCKS_SUNDAY_CALLS", True)
    sunday = datetime(2026, 9, 27, 12, 0, tzinfo=TZ)
    assert ("plan_offer", "call") in allowed(gate(cust(sunday_contact_permitted=True), CANDS, sunday))


def test_statutory_holiday_blocks_calls():
    assert datetime(2026, 12, 25).date() in holidays(2026)
    xmas = datetime(2026, 12, 25, 12, 0, tzinfo=TZ)
    assert ("plan_offer", "call") not in allowed(gate(cust(), CANDS, xmas))


def test_hardship_removes_pressure_and_routes_to_a_person():
    res = gate(cust(hardship_flag="clear"), CANDS, TUE_NOON)
    assert res.pressure_removed
    assert ("payment_link", "sms") not in allowed(res)
    assert res.route_to == "hardship_specialist"


def test_cease_contact_refuses_everything():
    res = gate(cust(contact_block="cease"), CANDS, TUE_NOON)
    assert not res.allowed and res.disposition != "allowed"


def test_gate_ignores_marketing_only_flags():
    res = gate(cust(national_dncl_flag=True, casl_consent=False), CANDS, TUE_NOON)
    assert len(res.allowed) == len(CANDS)


def test_allocator_fills_best_first_and_says_why_others_wait():
    rows = [
        {
            "case_id": f"C{i}",
            "treatment": "reminder",
            "channel": "sms",
            "window": "08-12",
            "priority": 100 - i,
            "assigned_agent_id": None,
            "alt_windows": [],
        }
        for i in range(5)
    ]
    out = allocator.allocate(rows, {("sms", "08-12"): 3})
    assert [r["status"] for r in sorted(out, key=lambda r: r["case_id"])] == ["scheduled"] * 3 + ["deferred"] * 2
    assert all(r["deferred_reason"] for r in out if r["status"] == "deferred")


def test_allocator_respects_agent_call_slots_and_outages():
    rows = [
        {
            "case_id": f"C{i}",
            "treatment": "plan_offer",
            "channel": "call",
            "window": "12-17",
            "priority": 10 - i,
            "assigned_agent_id": "AG-1",
            "alt_windows": [],
        }
        for i in range(3)
    ]
    out = allocator.allocate(rows, {("call", "12-17"): 10}, {"AG-1": 1})
    assert sum(r["status"] == "scheduled" for r in out) == 1
    out = allocator.allocate(rows, {("call", "12-17"): 10}, {"AG-1": 5}, outage={"call"})
    assert all(r["status"] == "deferred" for r in out)


def test_uplift_gate_needs_overlap_and_volume():
    from decisioning.nba import uplift_gate

    ok = {"reminder": 5000, "plan_offer": 1000}
    assert uplift_gate(0.70, ok)[0] is True
    assert uplift_gate(0.69, ok)[0] is False
    enabled, why = uplift_gate(0.9, {**ok, "plan_offer": 999})
    assert not enabled and "plan offer" in why


def test_batch_sample_is_two_percent_rounded_up_and_never_empty():
    from decisioning.nba import sample_size

    assert [sample_size(n) for n in (0, 1, 49, 50, 51, 500)] == [0, 1, 1, 1, 2, 10]


def test_days_before_payday_counts_from_the_due_date():
    from datetime import date

    from decisioning.promise_check import days_before_payday

    assert days_before_payday(date(2026, 10, 9), date(2026, 10, 15)) == 6
    assert days_before_payday(date(2026, 10, 16), date(2026, 10, 15)) == -1
    assert days_before_payday(date(2026, 10, 9), None) is None


def test_stress_rerun_defers_what_no_longer_fits_and_leaves_the_input_alone():
    from decisioning.stress_test import rerun

    rows = [
        {"case_id": f"C{i}", "treatment": "reminder", "channel": "call", "window": "all_day", "priority": 10.0 - i,
         "alt_windows": [], "assigned_agent_id": "A"}
        for i in range(3)
    ]
    cap = {("call", "all_day"): 5}
    before, after = rerun(rows, cap, {"A": 3}, channels_down={"call"})
    assert [r["status"] for r in before] == ["scheduled"] * 3
    assert [r["status"] for r in after] == ["deferred"] * 3
    assert "status" not in rows[0]
