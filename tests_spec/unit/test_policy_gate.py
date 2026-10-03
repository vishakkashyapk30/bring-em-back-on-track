"""Policy gate: plain contact rules applied before any model (V1 §6 UC1 Phase 1 step 1)."""

from __future__ import annotations

import datetime as dt

import pytest

from tests_spec import factories as F
from tests_spec import spec_constants as C
from tests_spec.helpers import contacts_customer, has_label, is_pressure

pytestmark = pytest.mark.policy_gate

OK_TIME = F.weekday_local(10, 30)  # Tuesday 10:30 Toronto


# ---------------------------------------------------------------------------
# Baseline
# ---------------------------------------------------------------------------
def test_unblocked_consented_customer_can_be_called_in_hours(adapter):
    """V1 §6 UC1 Phase 1 step 1: with consent, inside permitted hours, on a weekday and under the
    weekly limit, a call is permitted (sanity check that the gate is not blocking everything)."""
    res = adapter.policy_gate(F.customer_contact(), [F.action("reminder", "call", scheduled_at=OK_TIME)], OK_TIME)
    assert res.disposition == "contact_allowed"
    assert res.is_permitted(F.action("reminder", "call"))


# ---------------------------------------------------------------------------
# Hard blocks: cease, insolvency, deceased
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("block", ["cease", "insolvency", "deceased"])
@pytest.mark.parametrize("channel", C.CHANNELS)
def test_contact_blocks_stop_every_channel(adapter, block, channel):
    """V1 §6 UC1 Phase 1 step 1: "no contact after a stop request, insolvency or death".
    Contract `contact_block` enum (V1 Part 3). Applies to every channel, including letters."""
    cust = F.customer_contact(contact_block=block)
    res = adapter.policy_gate(cust, [F.action("reminder", channel, scheduled_at=OK_TIME)], OK_TIME)
    assert res.disposition == "no_contact"
    assert not any(contacts_customer(a) for a in res.permitted)


@pytest.mark.parametrize("block", ["cease", "insolvency", "deceased"])
def test_contact_blocks_hold_regardless_of_risk_or_treatment(adapter, block):
    """V1 §6 UC1 Phase 1 step 1 ("Before any model runs, plain rules remove what I must not do"):
    no treatment at all (not even a plan offer or a specialist referral) reaches a blocked customer."""
    cust = F.customer_contact(contact_block=block)
    res = adapter.policy_gate(cust, F.all_contact_actions(OK_TIME), OK_TIME)
    assert res.permitted == [] or all(a.treatment == "no_contact" for a in res.permitted)
    assert res.rules_fired, "the block must be explained (Brief: Explain every decision)"


def test_third_party_representative_routes_to_a_person(adapter):
    """V1 §6 UC1 Phase 1 step 1: "a representative sends the case to a person".
    Contract `contact_block = represented` (credit counselling / legal representative)."""
    for cust in (
        F.customer_contact(contact_block="represented"),
        F.customer_contact(third_party_rep_flag=True),
    ):
        res = adapter.policy_gate(cust, F.all_contact_actions(OK_TIME), OK_TIME)
        assert res.disposition == "route_to_person"
        assert not any(contacts_customer(a) for a in res.permitted), "no automated contact to the customer"


def test_open_dispute_pauses_the_case(adapter):
    """V1 §6 UC1 Phase 1 step 1: "a dispute pauses it" (v2: "Open dispute_status: account pauses")."""
    res = adapter.policy_gate(F.customer_contact(dispute_open_flag=True), F.all_contact_actions(OK_TIME), OK_TIME)
    assert res.disposition == "paused"
    assert not any(contacts_customer(a) for a in res.permitted)


# ---------------------------------------------------------------------------
# Consent per channel
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("channel", C.CONSENT_CHANNELS)
def test_channel_without_consent_is_not_allowed(adapter, channel):
    """V1 §6 UC1 Phase 1 step 1: "I use only consented channels". Contract consent_* columns."""
    consent = {ch: True for ch in C.CONSENT_CHANNELS}
    consent[channel] = False
    cust = F.customer_contact(consent=consent)
    res = adapter.policy_gate(cust, [F.action("reminder", channel, scheduled_at=OK_TIME)], OK_TIME)
    assert not res.is_permitted(F.action("reminder", channel))


@pytest.mark.parametrize("channel", C.CONSENT_CHANNELS)
def test_missing_consent_is_treated_as_no_consent(adapter, channel):
    """V1 Part 3 rule 4 (consent never null, most restrictive) and V1 §6 step 1: an unknown consent
    must not be read as permission."""
    consent = {ch: True for ch in C.CONSENT_CHANNELS}
    consent[channel] = None
    res = adapter.policy_gate(
        F.customer_contact(consent=consent), [F.action("reminder", channel, scheduled_at=OK_TIME)], OK_TIME
    )
    assert not res.is_permitted(F.action("reminder", channel))


def test_withdrawn_consent_on_one_channel_leaves_other_consented_channels(adapter):
    """V1 §6 UC1 Phase 1 step 1 (consent is per channel): Ryan has no push consent (Brief C360
    mock-up "Consent: Call 8am-8pm ET, SMS, email"), so push is blocked but SMS stays allowed."""
    cust = F.ryan_contact()
    cands = [F.action("reminder", "push", scheduled_at=OK_TIME), F.action("reminder", "sms", scheduled_at=OK_TIME)]
    res = adapter.policy_gate(cust, cands, OK_TIME)
    assert not res.is_permitted(F.action("reminder", "push"))
    assert res.is_permitted(F.action("reminder", "sms"))


def test_marketing_only_flags_do_not_block_collections_contact(adapter):
    """v2 §6 UC1 step 1: "national_dncl_flag and CASL consent are marketing-only per the dictionary,
    so the gate ignores them". (V1 is silent; v2 statement assumed still valid.)"""
    cust = F.customer_contact(national_dncl_flag=True, casl_consent=False)
    res = adapter.policy_gate(cust, [F.action("reminder", "call", scheduled_at=OK_TIME)], OK_TIME)
    assert res.is_permitted(F.action("reminder", "call"))


# ---------------------------------------------------------------------------
# Permitted hours, in the customer's own time zone
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "tz,local_hour,local_minute,allowed",
    [
        (F.TORONTO, 7, 59, False),
        (F.TORONTO, 9, 0, True),
        (F.TORONTO, 19, 30, True),
        (F.TORONTO, 21, 0, False),
        (F.TORONTO, 2, 0, False),
        (F.VANCOUVER, 7, 0, False),
        (F.VANCOUVER, 12, 0, True),
        (F.HALIFAX, 22, 15, False),
        ("America/St_Johns", 8, 30, True),
    ],
)
def test_calls_only_inside_permitted_hours_local_time(adapter, tz, local_hour, local_minute, allowed):
    """V1 §6 UC1 Phase 1 step 1 ("permitted hours") and V1 §6 UC1 ("a time window ... in the
    customer's time zone"); v2: "Calls only inside permitted_call_start_local to
    permitted_call_end_local"."""
    at = F.local_dt(tz, C.REFERENCE_WEEKDAY, local_hour, local_minute)
    cust = F.customer_contact(time_zone=tz)
    res = adapter.policy_gate(cust, [F.action("reminder", "call", scheduled_at=at)], at)
    assert res.is_permitted(F.action("reminder", "call")) is allowed


def test_same_instant_is_judged_in_each_customers_own_zone(adapter):
    """V1 §6 UC1: windows are "in the customer's time zone". 14:30 UTC on a Tuesday in October is
    10:30 in Toronto (allowed) but 07:30 in Vancouver (before 08:00, blocked)."""
    at = dt.datetime(2026, 10, 6, 14, 30, tzinfo=dt.UTC)
    toronto = adapter.policy_gate(F.customer_contact(time_zone=F.TORONTO), [F.action("reminder", "call", scheduled_at=at)], at)
    vancouver = adapter.policy_gate(F.customer_contact(time_zone=F.VANCOUVER), [F.action("reminder", "call", scheduled_at=at)], at)
    assert toronto.is_permitted(F.action("reminder", "call"))
    assert not vancouver.is_permitted(F.action("reminder", "call"))


def test_customer_specific_window_is_respected(adapter):
    """Contract `permitted_call_start_local` / `permitted_call_end_local` (V1 Part 3): a customer with a
    narrower 12:00-17:00 window cannot be called at 10:00 even though 10:00 is in a default window."""
    cust = F.customer_contact(permitted_call_start_local="12:00", permitted_call_end_local="17:00")
    at = F.weekday_local(10, 0)
    res = adapter.policy_gate(cust, [F.action("reminder", "call", scheduled_at=at)], at)
    assert not res.is_permitted(F.action("reminder", "call"))


def test_window_start_boundary(adapter):
    """Brief C360 mock-up "Call 8am-8pm ET": 08:00 local is inside the window (TBC inclusive)."""
    inclusive = C.require_constant(C.PERMITTED_WINDOW_START_INCLUSIVE, "PERMITTED_WINDOW_START_INCLUSIVE")
    at = F.weekday_local(8, 0)
    res = adapter.policy_gate(F.customer_contact(), [F.action("reminder", "call", scheduled_at=at)], at)
    assert res.is_permitted(F.action("reminder", "call")) is inclusive


def test_window_end_boundary(adapter):
    """Brief C360 mock-up "Call 8am-8pm ET": whether 20:00 itself is allowed is TBC."""
    exclusive = C.require_constant(C.PERMITTED_WINDOW_END_EXCLUSIVE, "PERMITTED_WINDOW_END_EXCLUSIVE")
    at = F.weekday_local(20, 0)
    res = adapter.policy_gate(F.customer_contact(), [F.action("reminder", "call", scheduled_at=at)], at)
    assert res.is_permitted(F.action("reminder", "call")) is (not exclusive)


# ---------------------------------------------------------------------------
# Sundays and holidays
# ---------------------------------------------------------------------------
def test_no_calls_on_sunday(adapter):
    """V1 §6 UC1 Phase 1 step 1: permitted hours "never Sundays or holidays"."""
    at = F.local_dt(F.TORONTO, C.REFERENCE_SUNDAY, 11, 0)
    res = adapter.policy_gate(F.customer_contact(), [F.action("reminder", "call", scheduled_at=at)], at)
    assert not res.is_permitted(F.action("reminder", "call"))


def test_sunday_flag_versus_v1_never_sundays(adapter):
    """V1 §6 step 1 "never Sundays" vs v2 "off Sundays unless sunday_contact_permitted".
    V1 is primary: SUNDAY_FLAG_UNLOCKS_SUNDAY_CALLS = False (see open_questions.md Q1)."""
    at = F.local_dt(F.TORONTO, C.REFERENCE_SUNDAY, 11, 0)
    cust = F.customer_contact(sunday_contact_permitted=True)
    res = adapter.policy_gate(cust, [F.action("reminder", "call", scheduled_at=at)], at)
    assert res.is_permitted(F.action("reminder", "call")) is C.SUNDAY_FLAG_UNLOCKS_SUNDAY_CALLS


def test_sunday_is_judged_in_local_time(adapter):
    """V1 §6 UC1 (customer's time zone) + V1 §6 step 1 "never Sundays": 02:30 UTC on Monday 12 Oct is
    still Sunday 19:30 in Vancouver (inside 08:00-20:00), so a Vancouver customer must not be called,
    even though it is Monday in UTC."""
    at = dt.datetime(2026, 10, 12, 2, 30, tzinfo=dt.UTC)
    res = adapter.policy_gate(
        F.customer_contact(time_zone=F.VANCOUVER), [F.action("reminder", "call", scheduled_at=at)], at
    )
    assert not res.is_permitted(F.action("reminder", "call"))


@pytest.mark.parametrize("holiday", C.UNAMBIGUOUS_HOLIDAYS, ids=lambda d: d.isoformat())
def test_no_calls_on_statutory_holidays(adapter, holiday):
    """V1 §6 UC1 Phase 1 step 1: "never Sundays or holidays" (calendar TBC; Canada Day and Christmas
    Day are national statutory holidays in every province)."""
    at = F.local_dt(F.TORONTO, holiday, 11, 0)
    res = adapter.policy_gate(F.customer_contact(), [F.action("reminder", "call", scheduled_at=at)], at)
    assert not res.is_permitted(F.action("reminder", "call"))


# ---------------------------------------------------------------------------
# Weekly contact limit
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("used,cap,allowed", [(0, 3, True), (2, 3, True), (3, 3, False), (4, 3, False), (1, 1, False)])
def test_weekly_contact_limit(adapter, used, cap, allowed):
    """V1 §6 UC1 Phase 1 step 1: "the weekly contact limit"; v2: "under contact_cap_7d"."""
    cust = F.customer_contact(contacts_last_7d=used, contact_cap_7d=cap)
    res = adapter.policy_gate(cust, [F.action("reminder", "call", scheduled_at=OK_TIME)], OK_TIME)
    assert res.is_permitted(F.action("reminder", "call")) is allowed


def test_contact_limit_block_is_explained_in_plain_words(adapter):
    """V1 §6 UC1 Phase 1 step 5 example: "No call: 3 of 3 contacts used this week"."""
    cust = F.customer_contact(contacts_last_7d=3, contact_cap_7d=3)
    res = adapter.policy_gate(cust, [F.action("reminder", "call", scheduled_at=OK_TIME)], OK_TIME)
    msgs = " | ".join(r.message for r in res.rules_fired)
    assert "3 of 3" in msgs, msgs


# ---------------------------------------------------------------------------
# Hardship and vulnerability
# ---------------------------------------------------------------------------
@pytest.mark.hardship
@pytest.mark.parametrize("hardship,vulnerable", [("possible", False), ("clear", False), ("none", True)])
def test_hardship_or_vulnerability_removes_pressure_and_routes_to_trained_agent(adapter, hardship, vulnerable):
    """V1 §6 UC1 Phase 1 step 1: "A hardship or vulnerability flag removes pressure actions and routes
    the case to a trained agent" (v2: a `vulnerable_customer_certified` agent)."""
    cust = F.customer_contact(hardship_flag=hardship, vulnerability_flag=vulnerable)
    res = adapter.policy_gate(cust, F.all_contact_actions(OK_TIME), OK_TIME)
    assert not any(is_pressure(a) for a in res.permitted)
    assert res.pressure_removed is True
    assert res.route_to and has_label(res.route_to, "certified", "trained", "specialist", "hardship")


@pytest.mark.hardship
def test_hardship_keeps_gentle_options_available(adapter):
    """V1 §10 Hardship latch: "a false alarm only costs a gentler contact" (v2 §9) -> a plan offer or
    specialist referral is still possible on a consented channel inside hours."""
    cust = F.customer_contact(hardship_flag="possible")
    res = adapter.policy_gate(cust, F.all_contact_actions(OK_TIME), OK_TIME)
    assert any(a.treatment in {"plan_offer", "specialist_referral"} for a in res.permitted)


# ---------------------------------------------------------------------------
# Fairness: protected attributes never influence the gate
# ---------------------------------------------------------------------------
@pytest.mark.fairness
@pytest.mark.parametrize("attr,a,b", F.single_attribute_variants())
def test_gate_outcome_ignores_each_protected_attribute(adapter, attr, a, b):
    """Brief ground rules "no protected attributes in decisions"; V1 §10: none of the 12 (plus age,
    age_band) "feed a model or a rule"."""
    ca = F.customer_contact(protected={attr: a})
    cb = F.customer_contact(protected={attr: b})
    cands = F.all_contact_actions(OK_TIME)
    ra, rb = adapter.policy_gate(ca, cands, OK_TIME), adapter.policy_gate(cb, cands, OK_TIME)
    key = lambda r: (r.disposition, sorted((x.treatment, x.channel) for x in r.permitted))  # noqa: E731
    assert key(ra) == key(rb)


@pytest.mark.explanation
def test_every_block_names_its_rule(adapter):
    """Brief ground rules "Explain every decision"; V1 §6 step 5: "which rules applied"."""
    cust = F.customer_contact(consent={"call": False, "sms": True, "email": True, "push": True})
    res = adapter.policy_gate(cust, [F.action("reminder", "call", scheduled_at=OK_TIME)], OK_TIME)
    assert res.blocked, "the call must be blocked"
    assert all(code for _, code in res.blocked)
    assert res.rules_fired and all(r.message.strip() for r in res.rules_fired)


def test_gate_is_deterministic(adapter):
    """V1 §8 "Where I deliberately avoid AI: Policy rules ... are plain rules": same input, same output."""
    cust = F.customer_contact(contacts_last_7d=2)
    cands = F.all_contact_actions(OK_TIME)
    r1, r2 = adapter.policy_gate(cust, cands, OK_TIME), adapter.policy_gate(cust, cands, OK_TIME)
    assert [(a.treatment, a.channel) for a in r1.permitted] == [(a.treatment, a.channel) for a in r2.permitted]
    assert [r.code for r in r1.rules_fired] == [r.code for r in r2.rules_fired]
