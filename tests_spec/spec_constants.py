"""Named constants taken from the specification documents.

Every value here is quoted from, or derived from, the docs. Where a value is marked
TBC or is ambiguous in the docs, it is flagged with ``TBC`` in the comment and
appears in open_questions.md. A value of ``None`` means "the spec does not settle
this". Tests that depend on a ``None`` constant skip (via ``require_constant``)
instead of guessing.

Abbreviations used in source citations:
  Brief = inputs/brief/problem_statement.md
  V1    = inputs/design/collections_system_design_V1.md   (primary spec)
  v2    = inputs/design/collections_system_design_v2.md   (earlier, shorter version)
  NI    = inputs/design/novel_ideas.md
"""

from __future__ import annotations

import datetime as _dt

import pytest

# ---------------------------------------------------------------------------
# Protected attributes and other excluded inputs (V1 §10 Governance; v2 §9)
# ---------------------------------------------------------------------------
PROTECTED_ATTRIBUTES: tuple[str, ...] = (
    "gender_code",
    "marital_status",
    "citizenship_status",
    "household_size",
    "dependants_count",
    "newcomer_program_flag",
    "newcomer_arrival_date",
    "accessibility_needs_flag",
    "accessibility_type",
    "vulnerability_type",
    "ccb_deposit_flag",
    "customer_accent_region",
)
# V1 §10: "I also leave out age, age band and voice characteristics."
# Contract rule 8: "the 12 in Governance, plus age, age_band".
ALSO_EXCLUDED_ATTRIBUTES: tuple[str, ...] = ("age", "age_band")
ALL_EXCLUDED_FROM_DECISIONS: tuple[str, ...] = PROTECTED_ATTRIBUTES + ALSO_EXCLUDED_ATTRIBUTES

# V1 §5: "From voice I use only call-level measures, never pitch, speaking speed or accent."
# v2 §5: "Pitch, energy, speaking rate, filler rate and customer_accent_region stay out".
FORBIDDEN_VOICE_FEATURE_KEYWORDS: tuple[str, ...] = (
    "pitch",
    "energy",
    "speaking_rate",
    "speaking_speed",
    "filler_rate",
    "accent",
)

# V1 §10: vulnerability_flag IS allowed because it can only make treatment gentler.
ALLOWED_SENSITIVE_FLAGS: tuple[str, ...] = ("vulnerability_flag", "hardship_flag")

# ---------------------------------------------------------------------------
# Small groups, cluster safety, identity (V1 §3, §4, §10; v2 §3)
# ---------------------------------------------------------------------------
SMALL_GROUP_MIN_SIZE = 10  # V1 §4 / §10 / NI S1, S2: hide any group with fewer than 10.
MAX_CRM_RECORDS_PER_AUTO_CLUSTER = 5  # V1 §3: "more than five CRM records goes to a person".
# v2 §3 only: "or with any internal pair below 0.5, go to review". V1 is silent. TBC.
MIN_INTERNAL_PAIR_PROBABILITY_V2 = 0.5
AUTO_LINK_PRECISION_TARGET = 0.995  # V1 §3: cut-off so 99.5% of automatic links are correct.

# ---------------------------------------------------------------------------
# Fairness gate (H4)
# ---------------------------------------------------------------------------
PROXY_AUC_THRESHOLD = 0.65  # V1 §5, NI H4: drop/coarsen a feature group with AUC above 0.65.

# ---------------------------------------------------------------------------
# Data contract (V1 Part 3)
# ---------------------------------------------------------------------------
C360_PRODUCT = "gold.c360_customer"
FRESHNESS_SLA_HOURS = 26  # V1 Part 3: `_refreshed_at` no older than 26 hours.
PAST_DUE_WARN_TOLERANCE_CAD = 1.0  # Rule 3: max_dpd = 0 with more than CAD 1 past due: warn.
EMPLOYER_MATCH_RATE_WARN = 0.90  # Rule 10, marked TBC in V1 Part 3. V1 only (not in v2).
CONTACT_BLOCK_VALUES = ("none", "cease", "insolvency", "deceased", "represented")
HARDSHIP_LEVELS = ("none", "possible", "clear")
MATCH_METHODS = ("deterministic", "probabilistic", "reviewed")
CONTRACT_MIN_QUALITY_RULES = 3  # Brief Part 1: "3+ quality rules".

# ---------------------------------------------------------------------------
# Policy gate and contact rules (V1 §6 UC1 Phase 1 step 1; v2 §6 step 1)
# ---------------------------------------------------------------------------
# The example explanation "No call: 3 of 3 contacts used this week" implies a cap of 3.
# The real cap is per customer (`contact_cap_7d`, v2). TBC.
EXAMPLE_CONTACT_CAP_7D = 3
# Which channels the permitted-hours rule applies to. v2 says "Calls only inside
# permitted_call_start_local to permitted_call_end_local". V1 says "permitted hours"
# without naming channels. We test calls only. TBC.
HOURS_RULE_CHANNELS: frozenset[str] = frozenset({"call"})
# Is the end of the permitted window exclusive (20:00 is outside)? Not stated. TBC.
PERMITTED_WINDOW_END_EXCLUSIVE: bool | None = True  # settled by the build team, see docs/profiling/profiling_decisions.md
PERMITTED_WINDOW_START_INCLUSIVE: bool | None = True  # "Call 8am-8pm" reads as 08:00 allowed.
# V1: "never Sundays or holidays". v2: "off Sundays unless sunday_contact_permitted".
# V1 is primary, so the flag does NOT unlock Sundays. Contradiction logged in OPEN_QUESTIONS.
SUNDAY_FLAG_UNLOCKS_SUNDAY_CALLS = False
# Holidays that are national statutory holidays everywhere in Canada (the calendar is TBC).
UNAMBIGUOUS_HOLIDAYS: tuple[_dt.date, ...] = (_dt.date(2026, 7, 1), _dt.date(2026, 12, 25))
# A plain Tuesday in Oct 2026 (DST in force in Canada until 1 Nov 2026).
REFERENCE_WEEKDAY = _dt.date(2026, 10, 6)
REFERENCE_SUNDAY = _dt.date(2026, 10, 11)

# "Pressure actions" are never defined in the docs. TBC. Our reading: collection reminders and
# payment links are pressure; a plan offer, a specialist referral and no contact are not.
PRESSURE_TREATMENTS: frozenset[str] = frozenset({"reminder", "payment_link"})
NON_PRESSURE_TREATMENTS: frozenset[str] = frozenset({"plan_offer", "specialist_referral", "no_contact"})

# ---------------------------------------------------------------------------
# NBA ladder, model and Phase 2 (V1 §6 UC1)
# ---------------------------------------------------------------------------
TREATMENTS = ("reminder", "payment_link", "plan_offer", "specialist_referral", "no_contact")
CHANNELS = ("call", "sms", "email", "push", "letter")
CONSENT_CHANNELS = ("call", "sms", "email", "push")  # Contract has consent_* for these four only.
# NI A1: channel_capacity.time_band offers only these bands. V1 names them morning, afternoon,
# evening, any time.
TIME_WINDOWS = ("morning", "afternoon", "evening", "any")
# "Low risk" / "high risk" cut-offs are not stated (TBC). Tests use extreme values only.
CLEARLY_LOW_RISK = 0.02
CLEARLY_HIGH_RISK = 0.97
REMINDER_DUE_WITHIN_DAYS = 3  # V1: "A high-risk one due within three days gets a reminder".
AGENT_CALL_MIN_DPD = 31  # V1: "Cases more than 30 days behind and at high risk get a call".
INCUMBENT_MODEL = "ptp_break v2.1"  # V1 §2, AUC 0.74.
INCUMBENT_AUC = 0.74
UPLIFT_MIN_OVERLAP_SHARE = 0.70  # V1 §6 Phase 2.
UPLIFT_MIN_CASES_PER_ACTION = 1000  # V1 §6 Phase 2.
# Features where "more late payments never lower the risk" (V1 §6 step 2). Exact list TBC.
MONOTONE_INCREASING_FEATURES = ("ptp_broken_count_90d", "dpd_max_current")
RESCORE_SLA_SECONDS = 5 * 60  # V1 §9: re-scored within five minutes.

# ---------------------------------------------------------------------------
# Human review (V1 §6 "Where a person reviews")
# ---------------------------------------------------------------------------
BATCH_SAMPLE_FRACTION = 0.02  # "approved as a batch, with 2% checked first".
# Rounding of the 2% sample (ceil? at least 1?) is not stated. TBC. We assume ceil, minimum 1.
BATCH_SAMPLE_MIN_ITEMS: int | None = 1
OVERRIDE_RATE_REVIEW_THRESHOLD = 0.25  # V1 §2: "Anything above 25% gets a review".
INDIVIDUAL_REVIEW_TREATMENTS = frozenset({"plan_offer"})  # Plan offers always one at a time.

# ---------------------------------------------------------------------------
# Post-call summary (V1 §6 UC2)
# ---------------------------------------------------------------------------
SUMMARY_MAX_WORDS = 80
ASR_CONFIDENCE_MIN: float | None = 0.80  # v2 §5 only, marked TBC.

# ---------------------------------------------------------------------------
# Hardship (V1 §10 latch; NI H2)
# ---------------------------------------------------------------------------
HARDSHIP_SOURCES = ("agent_coded", "customer_form", "model", "llm_flag")  # NI H2.
# Who may confirm (-> clear): "A specialist confirms it by linking a program."
HARDSHIP_CONFIRMING_ROLES = frozenset({"hardship_specialist"})
# Can a front-line agent (a person) lower the flag? "Only a person can lower it". The role is TBC.
AGENT_MAY_LOWER_HARDSHIP: bool | None = False  # settled by the build team, see docs/profiling/profiling_decisions.md
# Can a team lead confirm hardship? Not stated. TBC.
TEAM_LEAD_MAY_CONFIRM_HARDSHIP: bool | None = False  # settled by the build team, see docs/profiling/profiling_decisions.md

# ---------------------------------------------------------------------------
# Eligibility boundaries (V1 §6 UC3; v2 §6 UC3). All TBC.
# ---------------------------------------------------------------------------
MAX_DPD_INCLUSIVE: bool | None = True  # dpd == max_dpd is eligible? TBC.
MIN_MONTHS_ON_BOOK_INCLUSIVE: bool | None = True  # mob == min is eligible? TBC.
# max_uses_12m: is a customer with uses == max still eligible? Our reading: no (max reached). TBC.
USES_EQUAL_TO_MAX_IS_ELIGIBLE: bool | None = False  # settled by the build team, see docs/profiling/profiling_decisions.md
BROKEN_PLAN_LOOKBACK_DAYS = 90  # `excludes_broken_plan_90d`.
ELIGIBILITY_RULE_NAMES = (
    "max_dpd",
    "min_months_on_book",
    "max_uses_12m",
    "excludes_insolvency",
    "excludes_broken_plan_90d",
)

# ---------------------------------------------------------------------------
# Labels (exact strings from the docs; matched case-insensitively as substrings)
# ---------------------------------------------------------------------------
LABEL_MODEL_ESTIMATE = "model estimate, not cause and effect"  # V1 §6 step 4 (A2).
LABEL_MODEL_IMPLIED = "model-implied"  # NI A2 / V1 §8: accepted synonym for the same label.
LABEL_OBSERVED_NOT_CAUSAL = "observed, not causal"  # v2 §4, NI H1/S4.

# ---------------------------------------------------------------------------
# Metrics (V1 §2)
# ---------------------------------------------------------------------------
CURE_WINDOW_DAYS = 30

# ---------------------------------------------------------------------------
# SQL guard (V1 §4 step 3; v2 §4 step 4)
# ---------------------------------------------------------------------------
MAX_SQL_ROW_LIMIT: int | None = 1000  # settled by the build team, see docs/profiling/profiling_decisions.md
# Is `SELECT *` refused outright, or expanded to allowlisted columns? Not stated. TBC.
SELECT_STAR_REFUSED: bool | None = True  # settled by the build team, see docs/profiling/profiling_decisions.md

# ---------------------------------------------------------------------------
# Feature store (V1 §5)
# ---------------------------------------------------------------------------
PARITY_SAMPLE_SIZE = 1000
FEATURE_BUILT_BY = ("SQL", "AI", "voice")  # V1 §5. v2 uses "LLM" for AI. Match case-insensitively.

# ---------------------------------------------------------------------------
# Example incident (NI H5; v2 §4): INC-0914, 14 Sep app outage, est. 1,900 affected.
# ---------------------------------------------------------------------------
OUTAGE_INCIDENT_ID = "INC-0914"
OUTAGE_START = _dt.datetime(2026, 9, 14, 0, 0, tzinfo=_dt.UTC)
OUTAGE_END = _dt.datetime(2026, 9, 14, 23, 59, tzinfo=_dt.UTC)
OUTAGE_AFFECTED_EST = 1900

# ---------------------------------------------------------------------------
# Roles (V1 §10)
# ---------------------------------------------------------------------------
ROLES = ("agent", "hardship_specialist", "team_lead", "analyst", "data_steward")


def require_constant(value, name: str):
    """Skip the calling test when a spec constant is unresolved (None / TBC)."""
    if value is None:
        pytest.skip(f"Spec constant {name} is TBC in the docs; see open_questions.md")
    return value
