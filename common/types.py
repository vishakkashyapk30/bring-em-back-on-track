"""Enums shared by the API, decisioning and frontend contract."""

from enum import StrEnum


class Role(StrEnum):
    agent = "agent"
    hardship_specialist = "hardship_specialist"
    team_lead = "team_lead"
    analyst = "analyst"
    steward = "steward"


class HardshipLevel(StrEnum):
    none = "none"
    possible = "possible"
    clear = "clear"


class ContactBlock(StrEnum):
    none = "none"
    cease = "cease"
    insolvency = "insolvency"
    deceased = "deceased"
    represented = "represented"


class Treatment(StrEnum):
    reminder = "reminder"
    payment_link = "payment_link"
    plan_offer = "plan_offer"
    specialist_referral = "specialist_referral"
    no_contact = "no_contact"


PRESSURE_TREATMENTS = {Treatment.reminder, Treatment.payment_link}
"""Removed whenever hardship_flag is possible/clear or vulnerability_flag is set. Agent calls
for collection are also pressure; see decisioning.policy_gate."""


class Channel(StrEnum):
    call = "call"
    sms = "sms"
    email = "email"
    push = "push"
    letter = "letter"


class TimeBand(StrEnum):
    morning = "08-12"
    afternoon = "12-17"
    evening = "17-21"
    all_day = "all_day"


class Decision(StrEnum):
    approve = "approve"
    edit = "edit"
    override = "override"
