"""Adapter interface between this specification-based test suite and the system under test.

This file is written from the requirements only (Brief, V1, v2, novel ideas register).
It names the operations the docs imply, in business terms, and the small data shapes
they take and return. It assumes nothing about the implementation's modules, URLs or
framework.

HOW TO BIND
-----------
Write ``adapter_impl.py`` (anywhere importable) with a factory that returns an object
implementing :class:`SpecAdapter`. The easiest way is to subclass
:class:`SpecAdapterBase`, whose every method raises ``NotImplementedError``, and override
what you support. Then run with::

    SPEC_ADAPTER=adapter_impl:make_adapter pytest tests_spec

Any operation that raises ``NotImplementedError`` makes the tests that use it SKIP,
not fail. The system-level journeys use :meth:`SpecAdapter.system_client`.

CONVENTIONS
-----------
* All enumerations are plain lower-case strings (see the ``Literal`` aliases). Values come
  from the docs: e.g. treatments ``reminder | payment_link | plan_offer |
  specialist_referral | no_contact`` (v2 §6) and hardship ``none | possible | clear``.
* Timestamps are timezone-aware ``datetime``. Local times use IANA zone names
  (``America/Toronto``).
* Money is ``float`` CAD. Fractions are 0..1 (``0.25`` means 25%).
* A forbidden operation either raises ``PermissionError`` or returns a result with
  ``allowed=False``. Tests accept both.
* Source tables passed to ``load_sources`` / ``SystemClient.seed`` use the data-dictionary
  table and column names quoted in the docs (``customers``, ``card_accounts``,
  ``deposit_accounts.payroll_delay_days``, ...). The binding maps them to its own loaders.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------
Treatment = Literal["reminder", "payment_link", "plan_offer", "specialist_referral", "no_contact"]
Channel = Literal["call", "sms", "email", "push", "letter"]
TimeWindow = Literal["morning", "afternoon", "evening", "any"]
HardshipLevel = Literal["none", "possible", "clear"]
ContactBlock = Literal["none", "cease", "insolvency", "deceased", "represented"]
Role = Literal["agent", "hardship_specialist", "team_lead", "analyst", "data_steward"]
ActorKind = Literal["person", "model", "rule", "llm"]
GateDisposition = Literal["contact_allowed", "no_contact", "route_to_person", "paused"]
ReviewMode = Literal["individual", "batch"]
MatchMethod = Literal["deterministic", "probabilistic", "reviewed"]
Severity = Literal["error", "warn"]


# ---------------------------------------------------------------------------
# Shared small types
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Actor:
    """Who or what performs an operation. ``kind='person'`` requires a ``role``."""

    kind: ActorKind
    actor_id: str
    role: Role | None = None


@dataclass
class UserContext:
    """The signed-in person for in-process Layer 2 calls (role drives allowlists and row filters)."""

    user_id: str
    role: Role
    team_id: str | None = None


@dataclass
class ActionResult:
    """Outcome of a state-changing request in the system client."""

    allowed: bool
    status: str = ""  # e.g. "approved", "pending_approval", "refused", "stopped"
    record_id: str | None = None
    audit_id: str | None = None
    reason: str | None = None


@dataclass
class AuditRecord:
    """One append-only audit row (V1 §10: query, score, decision, edit, override, simulator run)."""

    audit_id: str
    event_type: str  # query | score | decision | edit | override | approval | simulator_run | hardship_change | ...
    actor_id: str
    actor_role: str | None
    subject_id: str | None  # golden_id, case_id, decision_id, batch_id, ...
    at: dt.datetime
    details: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None


# ---------------------------------------------------------------------------
# Layer 1: identity, golden record, data contract, data health
# ---------------------------------------------------------------------------
@dataclass
class SourceRecord:
    """One customer-bearing row from a source system, before matching (V1 §3)."""

    source_system: str  # crm | cards | loans | deposits | bureau
    source_key: str  # e.g. "C-88213", unique within source_system
    raw_name: str | None = None  # e.g. "R. MITCHELL", "MITCHELL, RYAN JAMES"
    first_name: str | None = None
    last_name: str | None = None
    preferred_name: str | None = None
    dob_raw: str | None = None  # any of the four source formats
    phone: str | None = None
    postal_code: str | None = None
    national_id_hash: str | None = None
    duplicate_of_crm_id: str | None = None
    crm_customer_id: str | None = None  # e.g. account_monthly_snapshot.crm_customer_id
    bank_subject_ref: str | None = None  # external.bank_subject_ref
    src_customer_ref: str | None = None  # deposits src_customer_ref / CIF
    pad_source_account: str | None = None
    is_current: bool = True  # CRM: effective_to_ts = 9999-12-31
    effective_from: dt.date | None = None
    email: str | None = None
    email_verified: bool | None = None
    email_bounced: bool | None = None
    consent: dict[str, bool | None] = field(default_factory=dict)  # channel -> consent
    cease_communication_flag: bool = False
    hardship_flag: HardshipLevel = "none"
    vulnerability_flag: bool = False
    protected: dict[str, Any] = field(default_factory=dict)  # raw protected attributes, if any


@dataclass
class IdentityCluster:
    golden_id: str
    members: list[str]  # "source_system:source_key"
    match_method: MatchMethod
    match_confidence: float  # lowest link probability in the cluster (contract)
    status: Literal["linked", "pending_review"] = "linked"


@dataclass
class IdentityReviewItem:
    """A pair or cluster sent to a data steward (V1 §3 pass 3)."""

    item_id: str
    member_keys: list[str]
    reason: str  # e.g. "cluster_size", "borderline_probability"
    masked_view: dict[str, Any] = field(default_factory=dict)  # what the LLM adjudicator / steward sees
    llm_suggestion: str | None = None
    decided: bool = False


@dataclass
class ResolutionResult:
    clusters: list[IdentityCluster]
    review_queue: list[IdentityReviewItem] = field(default_factory=list)
    golden_records: dict[str, GoldenRecord] = field(default_factory=dict)

    def golden_id_of(self, member_key: str) -> str | None:
        for c in self.clusters:
            if member_key in c.members:
                return c.golden_id
        return None


@dataclass
class GoldenRecord:
    """A ``gold.c360_customer`` row (V1 Part 3 schema), plus lineage for the C360 screen."""

    golden_id: str
    crm_customer_ids: list[str] = field(default_factory=list)
    source_ids: list[str] = field(default_factory=list)
    match_method: MatchMethod | None = None
    match_confidence: float | None = None
    display_name: str | None = None
    date_of_birth: dt.date | None = None
    email_token: str | None = None
    phone_token: str | None = None
    province_code: str | None = None
    fsa: str | None = None
    time_zone: str | None = None
    preferred_language: str | None = None
    consent: dict[str, bool | None] = field(default_factory=dict)
    permitted_call_start_local: str | None = None
    permitted_call_end_local: str | None = None
    contact_block: ContactBlock = "none"
    hardship_flag: HardshipLevel = "none"
    vulnerability_flag: bool = False
    dispute_open_flag: bool = False
    employer_key: str | None = None
    payroll_delay_days: int | None = None
    max_dpd: int | None = None
    total_past_due_cad: float | None = None
    open_case_id: str | None = None
    refreshed_at: dt.datetime | None = None
    lineage: dict[str, list[str]] = field(default_factory=dict)  # column -> source tables
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class C360Snapshot:
    """Tables handed to the contract quality rules. Keys use contract / dictionary names:
    ``c360_customer``, ``crm_current`` (current CRM rows with ``golden_id``,
    ``national_id_hash`` and consent columns), ``c360_account``, ``hardship_flag_events``,
    ``employer_match_sample``."""

    tables: dict[str, list[dict[str, Any]]]


@dataclass
class QualityRuleResult:
    rule_id: int  # 1..10 as numbered in V1 Part 3
    passed: bool
    severity: Severity
    failing_keys: list[str] = field(default_factory=list)
    message: str = ""


@dataclass
class QualityReport:
    results: list[QualityRuleResult]
    publish_blocked: bool

    def rule(self, rule_id: int) -> QualityRuleResult:
        for r in self.results:
            if r.rule_id == rule_id:
                return r
        raise AssertionError(f"quality rule {rule_id} missing from report")


@dataclass
class ContractColumn:
    name: str
    dtype: str
    pii_class: str
    source_rule: str = ""


@dataclass
class DataContract:
    product: str
    version: str
    owner: str
    steward: str
    policy_approver: str
    grain: str
    consumers: list[str]
    refresh: str
    freshness_sla_hours: float
    retention: str
    columns: list[ContractColumn]
    quality_rules: list[str]
    allowed_uses: list[str]
    prohibited_uses: list[str]


@dataclass
class ProposedFix:
    fix_id: str
    description: str
    status: str  # must start as "pending_engineer_approval"; never auto-applied
    applied: bool = False


@dataclass
class DriftReport:
    table: str
    added_columns: list[str]
    removed_columns: list[str]
    row_count_change: float | None = None
    null_rate_changes: dict[str, float] = field(default_factory=dict)
    explanation_sources: list[str] = field(default_factory=list)  # release notes / ops_events ids
    proposed_fix: ProposedFix | None = None


@dataclass
class OpsEvent:
    """An ``ops_events`` row (NI H5, S3, S5)."""

    event_id: str
    event_type: str  # outage | data_feed_issue | platform_release | external_economic | ...
    start_ts: dt.datetime
    end_ts: dt.datetime
    description: str = ""
    affected_tables: list[str] = field(default_factory=list)
    affected_customers_est: int | None = None
    payment_posting_affected: bool = True


@dataclass
class RepaymentRecord:
    """A due item and when it was paid (card_statements / loan_instalments / promises_to_pay)."""

    account_id: str
    golden_id: str
    due_date: dt.date
    paid_date: dt.date | None
    fees_charged: float = 0.0
    fees_reversed: float = 0.0


@dataclass
class OutageVictimReport:
    candidates: list[str]  # account ids
    our_count: int
    bank_estimate: int | None
    is_candidate_list: bool  # V1 §3: "a candidate list, not a final answer"
    proposals: list[ProposedAction] = field(default_factory=list)


@dataclass
class ProposedAction:
    """Something the system proposes that a person must approve (playbooks, H5, S1)."""

    proposal_id: str
    kind: str  # fee_reversal | pressure_hold | reprioritise | eligibility_precheck | contact
    subject_id: str
    status: str  # pending_approval | approved | rejected
    requires_role: Role | None = None
    requires_policy_office_signoff: bool = False


# ---------------------------------------------------------------------------
# Layer 2: questions, SQL guard, documents, analyst views
# ---------------------------------------------------------------------------
@dataclass
class QuestionTokens:
    """The editable chips the question was parsed into (V1 §4 step 1)."""

    metric: str | None = None
    dimensions: list[str] = field(default_factory=list)
    filters: dict[str, Any] = field(default_factory=dict)
    time_period: str | None = None
    sort: str | None = None


@dataclass
class Coverage:
    """Pre-flight (S5): how much of the portfolio the answer covers."""

    rows_or_customers: int
    portfolio_total: int


@dataclass
class AskAnswer:
    refused: bool
    refusal_reason: str | None = None
    refused_parts: list[str] = field(default_factory=list)  # which part was not allowed
    tokens: QuestionTokens | None = None
    sql: str | None = None
    rows: list[dict[str, Any]] = field(default_factory=list)
    data_products: list[str] = field(default_factory=list)
    freshness: dt.datetime | None = None
    caveats: list[str] = field(default_factory=list)
    incidents: list[str] = field(default_factory=list)  # ops_events ids flagged in the period
    coverage: Coverage | None = None
    insight_text: str | None = None
    follow_ups: list[str] = field(default_factory=list)
    suppressed_groups: int = 0


@dataclass
class SqlCheck:
    ok: bool
    violations: list[str] = field(default_factory=list)  # read_only | column_not_allowed | missing_limit | ...
    final_sql: str | None = None  # SQL as it would run (row filter / limit applied)
    effective_row_limit: int | None = None
    row_filter_applied: bool = False


@dataclass
class ReferenceDocument:
    doc_id: str
    section: str
    text: str
    doc_type: str = "policy"  # policy | release_note | agent_note | ...
    applies_to_products: list[str] = field(default_factory=list)
    applies_to_provinces: list[str] = field(default_factory=list)
    language: str = "EN"
    version: str = "1"
    superseded_by: str | None = None
    related_table: str | None = None


@dataclass
class PolicyQuery:
    question: str
    product: str
    province: str
    language: str = "EN"


@dataclass
class Citation:
    doc_id: str
    section: str


@dataclass
class PolicyAnswer:
    answered: bool
    text: str | None = None
    citations: list[Citation] = field(default_factory=list)
    refusal_reason: str | None = None


@dataclass
class ScorecardRow:
    strategy_code: str
    segment: dict[str, Any]  # e.g. {"entry_dpd_band": "31-60", "product": "card"}
    cure_rate: float | None
    cost_per_cure: float | None = None
    complaints_per_1000: float | None = None
    causal: bool = False
    label: str = ""


@dataclass
class EmployerObservation:
    """One customer-week for the employer radar (S1)."""

    golden_id: str
    employer_key: str
    industry_naics2: str
    week_start: dt.date
    payroll_gap: bool
    new_ei_deposit: bool
    payroll_amount_change_pct: float = 0.0
    has_open_case: bool = False
    exposure_cad: float = 0.0
    days_past_due: int = 0


@dataclass
class RadarRow:
    employer_key: str
    n_customers: int
    n_payroll_gap: int
    n_new_ei: int
    pattern: Literal["layoff_like", "payroll_delay", "none"]
    explained_by_incident: str | None = None
    open_cases: int = 0
    exposure_cad: float = 0.0
    label: str = ""


@dataclass
class AreaObservation:
    golden_id: str
    fsa: str
    ptp_broken: bool
    rolled_forward: bool


@dataclass
class MapBubble:
    area: str
    n_customers: int
    broken_promise_rate: float
    roll_rate: float


@dataclass
class MapResult:
    bubbles: list[MapBubble]
    sql: str | None
    suppressed_areas: int = 0


# ---------------------------------------------------------------------------
# Layer 3: feature store
# ---------------------------------------------------------------------------
@dataclass
class FeatureDefinition:
    name: str
    entity: str
    dtype: str
    source: str
    refresh: str
    owner: str
    version: str
    built_by: str  # SQL | AI (LLM) | voice
    prompt_version: str | None = None  # required when built_by is AI/LLM
    label_accuracy: float | None = None  # accuracy against hand labels, AI features


@dataclass
class FeatureValue:
    value: Any
    available_ts: dt.datetime | None  # the time the value could first have been known
    present: bool = True  # False for missing text/voice features (no transcript, poor audio)
    version: str | None = None


@dataclass
class FeatureVector:
    entity_id: str
    values: dict[str, FeatureValue]


@dataclass
class ParityReport:
    sampled: int
    mismatches: int
    alert_raised: bool


@dataclass
class ProxyGroupResult:
    group: str
    max_auc: float
    worst_protected_attribute: str | None
    decision: Literal["keep", "drop", "coarsen"]


@dataclass
class ProxyGateReport:
    groups: dict[str, ProxyGroupResult]


# ---------------------------------------------------------------------------
# Layer 4: policy gate, NBA, explanations
# ---------------------------------------------------------------------------
@dataclass
class CustomerContact:
    """The policy-relevant view of a customer and case, as the gate sees it (V1 §6 step 1)."""

    golden_id: str
    time_zone: str = "America/Toronto"
    province_code: str = "ON"
    consent: dict[str, bool | None] = field(
        default_factory=lambda: {"call": True, "sms": True, "email": True, "push": True}
    )
    permitted_call_start_local: str = "08:00"
    permitted_call_end_local: str = "20:00"
    sunday_contact_permitted: bool = False
    contact_block: ContactBlock = "none"
    third_party_rep_flag: bool = False
    dispute_open_flag: bool = False
    hardship_flag: HardshipLevel = "none"
    vulnerability_flag: bool = False
    contacts_last_7d: int = 0
    contact_cap_7d: int = 3
    national_dncl_flag: bool = False  # marketing-only (v2): must be ignored by the gate
    casl_consent: bool | None = None  # marketing-only (v2): must be ignored by the gate
    days_past_due: int = 38
    protected: dict[str, Any] = field(default_factory=dict)


@dataclass
class Action:
    """An NBA action = (treatment, channel, window) (V1 §6 UC1)."""

    treatment: Treatment
    channel: Channel | None = None
    window: TimeWindow | None = None
    scheduled_at: dt.datetime | None = None  # concrete instant, tz-aware, when known
    program_id: str | None = None


@dataclass
class RuleFired:
    code: str  # e.g. contact_cap, no_consent, outside_hours, sunday, holiday, cease, hardship
    message: str  # plain text, e.g. "No call: 3 of 3 contacts used this week"


@dataclass
class GateResult:
    disposition: GateDisposition
    permitted: list[Action]
    blocked: list[tuple[Action, str]]  # (action, rule code)
    rules_fired: list[RuleFired] = field(default_factory=list)
    route_to: str | None = None  # e.g. "person", "vulnerable_customer_certified"
    pressure_removed: bool = False

    def is_permitted(self, action: Action) -> bool:
        return any(
            a.treatment == action.treatment and a.channel == action.channel for a in self.permitted
        )


@dataclass
class PromiseInfo:
    ptp_id: str
    amount: float
    due_date: dt.date
    status: str  # open | kept | broken | partially_kept | cancelled
    created_ts: dt.datetime | None = None


@dataclass
class CaseSnapshot:
    """What NBA needs about one open case (built from C360 + features)."""

    case_id: str
    customer: CustomerContact
    product: str = "card"
    days_past_due: int = 38
    amount_at_risk_cad: float = 1200.0
    open_promise: PromiseInfo | None = None
    last_broken_promise: PromiseInfo | None = None
    payroll_delay_days: int = 0
    expected_next_payroll_date: dt.date | None = None
    contact_cost_cad: float = 1.0
    features: dict[str, Any] = field(default_factory=dict)


@dataclass
class Explanation:
    """Fixed-format, template-written explanation (V1 §6 step 5; v2 'no LLM')."""

    rules_applied: list[str]  # e.g. "No call: 3 of 3 contacts used this week"
    risk_reasons: list[str]  # e.g. "Payroll 29 days late"
    changes: list[str]  # e.g. "Promise PTP-0090311 broken"
    text: str
    generated_by: str  # must be "template" (never an LLM)


@dataclass
class NbaDecision:
    decision_id: str
    case_id: str
    action: Action
    break_probability: float | None
    expected_value: float | None
    explanation: Explanation
    review_mode: ReviewMode
    status: str = "proposed"  # proposed | approved | overridden | sent
    route_to: str | None = None
    model_version: str | None = None
    alternatives: list[Action] = field(default_factory=list)


@dataclass
class ModelEval:
    model_id: str
    auc: float
    evaluated_on: str  # identifier of the out-of-time promise set


@dataclass
class UpliftGate:
    enabled: bool
    reason: str


@dataclass
class ChannelCapacity:
    """Day capacity by channel and agent call slots (channel_capacity, agent_shifts)."""

    units_by_channel: dict[str, int]
    agent_call_slots: int


@dataclass
class DailyPlan:
    scheduled: list[NbaDecision]
    deferred: list[NbaDecision]


@dataclass
class StressScenario:
    name: str
    channel_outages: list[str] = field(default_factory=list)  # e.g. ["call"] for a dialer outage
    agent_absence_fraction: float = 0.0


@dataclass
class StressResult:
    plan: DailyPlan
    moved: list[tuple[str, str]]  # (decision_id, where it moved: channel or "next_day")
    original_unchanged: bool


@dataclass
class PromiseOutcome:
    ptp_id: str
    status: str  # open | kept | broken | partially_kept | cancelled
    due_date: dt.date
    grace_days: int = 0


@dataclass
class PromiseDraft:
    case_id: str
    amount: float
    due_date: dt.date


@dataclass
class PayrollInfo:
    expected_next_payroll_date: dt.date | None
    customer_stated_income_date: dt.date | None = None
    payroll_delay_days: int = 0


@dataclass
class PromiseCheck:
    """A2: 'this date is N days before your stated payday' and the live risk."""

    days_before_payday: int | None
    break_probability: float | None
    label: str  # "a model estimate, not cause and effect"
    saved: bool = False  # a what-if never saves anything by itself


# ---------------------------------------------------------------------------
# Hardship latch, programs, simulator (V1 §6 UC3, §10; NI H1, H2, H3)
# ---------------------------------------------------------------------------
@dataclass
class HardshipState:
    golden_id: str
    level: HardshipLevel
    program_id: str | None = None


@dataclass
class HardshipFlagEvent:
    golden_id: str
    from_level: HardshipLevel
    to_level: HardshipLevel
    actor_id: str
    actor_kind: ActorKind
    source: str | None  # agent_coded | customer_form | model | llm_flag
    reason: str | None
    at: dt.datetime
    program_id: str | None = None


@dataclass
class HardshipTransitionResult:
    accepted: bool
    new_level: HardshipLevel
    event: HardshipFlagEvent | None = None
    refusal_reason: str | None = None


@dataclass
class HardshipProgram:
    """A ``hardship_programs`` row."""

    program_id: str
    product_types: list[str]
    max_dpd: int
    min_months_on_book: int
    max_uses_12m: int
    excludes_insolvency: bool
    excludes_broken_plan_90d: bool
    requires_income_evidence: bool
    payment_reduction_pct: float  # fraction, 0.5 = 50%
    duration_months: int
    term_extension_max_months: int = 0
    rate_override: float | None = None  # annual rate during the plan; None = no rate lever
    fees_waived_flag: bool = False
    approver_level: str = "hardship_specialist"
    min_hardship_level: HardshipLevel = "possible"


@dataclass
class EligibilityInput:
    golden_id: str
    product: str
    days_past_due: int
    months_on_book: int
    program_uses_12m: int
    insolvency: bool
    broken_plan_last_90d: bool
    hardship_flag: HardshipLevel = "possible"
    income_evidence_on_file: bool = False
    free_text_notes: str | None = None  # must never change the outcome
    protected: dict[str, Any] = field(default_factory=dict)  # must never change the outcome


@dataclass
class EligibilityRuleResult:
    rule: str  # one of spec_constants.ELIGIBILITY_RULE_NAMES (plus optional extras)
    passed: bool
    detail: str = ""


@dataclass
class EligibilityResult:
    program_id: str
    eligible: bool
    rule_results: list[EligibilityRuleResult]
    decided_by: str  # must be "rules"
    payment_reduction_pct: float | None = None
    duration_months: int | None = None
    requires_income_evidence: bool | None = None


@dataclass
class LoanTerms:
    account_id: str
    principal_balance: float
    accrued_interest: float
    fees_outstanding: float
    interest_rate: float  # annual, fraction
    scheduled_payment_amount: float  # monthly
    remaining_term_months: int
    past_due_amount: float = 0.0


@dataclass
class CardTerms:
    account_id: str
    current_balance: float
    purchase_apr: float
    minimum_payment_due: float


@dataclass
class Affordability:
    payroll_avg_amount_3m: float  # monthly income
    essential_spend_amount_mtd: float  # already includes rent (V1 §6 UC3)
    other_lender_payment_amount_mtd: float
    as_of: dt.date  # used to scale MTD to a full month
    monthly_housing_cost: float | None = None  # must NOT be subtracted again
    protected: dict[str, Any] = field(default_factory=dict)  # household_size etc.: never used


@dataclass
class PlanLevers:
    term_extension_months: int = 0
    payment_reduction_pct: float = 0.0  # fraction
    rate_override: float | None = None  # annual rate during the plan
    payment_holiday_months: int = 0
    fee_waiver: bool = False


@dataclass
class PlanRequest:
    golden_id: str
    account: LoanTerms | CardTerms
    program: HardshipProgram
    levers: PlanLevers
    affordability: Affordability
    total_exposure: float
    expected_loss_est: float
    requested_by: Actor


@dataclass
class PlanScenario:
    scenario_id: str
    new_payment: float
    baseline_payment: float
    monthly_surplus: float
    payment_to_surplus_ratio: float | None
    months_to_clear: float | None
    baseline_months_to_clear: float | None
    total_interest: float | None
    baseline_total_interest: float | None
    total_customer_paid: float | None
    bank_value_plan: float | None
    status_quo_value: float | None
    plan_hold_rate: float | None
    plan_hold_label: str
    within_program_rules: bool
    approver_level_required: str | None
    rejected_levers: list[str] = field(default_factory=list)
    assumptions: dict[str, Any] = field(default_factory=dict)  # stated, e.g. discount_rate, lgd
    eligibility: EligibilityResult | None = None


@dataclass
class ReviewBoardRow:
    golden_id: str
    vulnerability_review_date: dt.date | None
    hardship_flag: HardshipLevel
    hardship_source: str | None


@dataclass
class MissedOfferReport:
    missed: list[str]  # case ids: hardship set, never offered a program (newest first)
    overridden_offers: list[dict[str, Any]]  # offers with eligibility_result = ineligible_overridden
    decline_reasons: dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Post-call summary (V1 §6 UC2)
# ---------------------------------------------------------------------------
@dataclass
class TranscriptTurn:
    turn_index: int
    speaker: Literal["agent", "customer"]
    text: str
    start_sec: float = 0.0
    end_sec: float = 0.0


@dataclass
class Transcript:
    contact_id: str
    case_id: str
    golden_id: str
    turns: list[TranscriptTurn]
    asr_confidence_avg: float = 0.95
    call_end_ts: dt.datetime | None = None


@dataclass
class RecordedPromise:
    """The promises_to_pay row created on the same contact_id."""

    ptp_id: str
    contact_id: str
    amount: float
    due_date: dt.date


@dataclass
class SummaryPromise:
    amount: float | None = None
    due_date: dt.date | None = None
    intent_strength: float | None = None  # 0..1


@dataclass
class SummaryDraft:
    draft_id: str
    contact_id: str
    summary: str
    promise: SummaryPromise
    signals: dict[str, Any]  # hardship_signal, stated_delay_reason, dispute_signal, complaint, vulnerability
    next_steps: list[str]
    citations: dict[str, list[int]]  # field name -> turn indexes supporting it
    mismatches: list[str]  # fields that disagree with the recorded promise (highlighted)
    schema_valid: bool
    status: str = "draft"  # draft | approved


@dataclass
class ApprovedSummary:
    draft_id: str
    approved_by: str
    saved_fields: dict[str, Any]
    edited_fields: list[str]
    audit_id: str | None = None


# ---------------------------------------------------------------------------
# Human review: batches
# ---------------------------------------------------------------------------
@dataclass
class ApprovalBatch:
    batch_id: str
    item_ids: list[str]  # decision ids
    sample_item_ids: list[str]  # the 2% checked first
    excluded_item_ids: list[str] = field(default_factory=list)  # items that need one-by-one review
    status: str = "pending"  # pending | sample_reviewed | approved | stopped


# ---------------------------------------------------------------------------
# Observability for governance tests
# ---------------------------------------------------------------------------
@dataclass
class LlmRequest:
    purpose: str  # question_parse | identity_adjudication | summary | policy_answer | text_feature | ...
    prompt_text: str
    model_host: str  # "bank_hosted" | "external" | ...


@dataclass
class OutboundMessage:
    """Something that actually left (or was queued to leave) for a customer."""

    message_id: str
    golden_id: str
    channel: Channel
    decision_id: str | None
    approved_by: str | None
    sent_at: dt.datetime | None


@dataclass
class MonitoringSnapshot:
    override_rate: float | None
    override_review_triggered: bool
    pressure_on_hardship_count: int
    contact_cap_breach_count: int
    out_of_hours_contact_count: int
    refusal_count: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# System-level views
# ---------------------------------------------------------------------------
@dataclass
class QueueItem:
    decision_id: str
    case_id: str
    golden_id: str
    action: Action
    review_mode: ReviewMode
    explanation: Explanation
    assigned_agent_id: str | None = None


@dataclass
class CustomerView:
    """The C360 screen (Brief Layer 1 mock-up) as the signed-in role sees it."""

    golden_id: str
    fields: dict[str, Any]  # visible fields; masked values appear as masked strings
    masked_fields: set[str]
    badges: dict[str, Any]  # risk, bucket, consent, hardship
    source_ids: list[str]
    match_confidence: float | None
    lineage: dict[str, list[str]]
    timeline: list[dict[str, Any]] = field(default_factory=list)
    nba: NbaDecision | None = None


# ---------------------------------------------------------------------------
# In-process adapter (unit + integration)
# ---------------------------------------------------------------------------
@runtime_checkable
class SpecAdapter(Protocol):
    # --- lifecycle and data loading (integration) ---
    def reset(self) -> None: """Return the system to an empty, isolated state."""
    def load_sources(self, tables: Mapping[str, list[dict[str, Any]]]) -> None: """Load raw source rows by dictionary table name."""
    def run_pipeline(self, as_of: dt.datetime) -> QualityReport: """Bronze -> silver -> gold -> features, as the nightly batch does."""
    def system_client(self) -> SystemClient: ...

    # --- Layer 1 ---
    def resolve_identities(self, records: Sequence[SourceRecord], previous: ResolutionResult | None = None) -> ResolutionResult: ...
    def find_golden_id(self, source_system: str, source_key: str) -> str | None: ...
    def get_golden_record(self, golden_id: str) -> GoldenRecord: ...
    def run_quality_rules(self, snapshot: C360Snapshot, now: dt.datetime) -> QualityReport: ...
    def get_data_contract(self, product: str) -> DataContract: ...
    def detect_schema_drift(self, table: str, baseline_batch: list[dict[str, Any]], new_batch: list[dict[str, Any]]) -> DriftReport: ...
    def find_outage_victims(self, event: OpsEvent, repayments: Sequence[RepaymentRecord]) -> OutageVictimReport: ...

    # --- Layer 2 ---
    def parse_question(self, question: str, user: UserContext) -> QuestionTokens: ...
    def ask(self, question: str, user: UserContext, token_overrides: QuestionTokens | None = None) -> AskAnswer: ...
    def validate_sql(self, sql: str, user: UserContext) -> SqlCheck: ...
    def suppress_small_groups(self, rows: list[dict[str, Any]], count_field: str) -> list[dict[str, Any]]: ...
    def load_reference_documents(self, docs: Sequence[ReferenceDocument]) -> None: ...
    def answer_policy_question(self, query: PolicyQuery, user: UserContext) -> PolicyAnswer: ...
    def strategy_scorecard(self, cases: Sequence[Mapping[str, Any]]) -> list[ScorecardRow]: ...
    def cure_rate_30d(self, cases: Sequence[Mapping[str, Any]]) -> float | None: ...
    def employer_radar(self, observations: Sequence[EmployerObservation], ops_events: Sequence[OpsEvent] = ()) -> list[RadarRow]: ...
    def weather_map(self, observations: Sequence[AreaObservation]) -> MapResult: ...

    # --- Layer 3 ---
    def get_feature_registry(self) -> list[FeatureDefinition]: ...
    def get_features_online(self, entity_id: str, names: Sequence[str]) -> FeatureVector: ...
    def get_features_offline(self, entity_id: str, as_of: dt.datetime, names: Sequence[str]) -> FeatureVector: ...
    def run_parity_check(self, sample_size: int) -> ParityReport: ...
    def proxy_feature_gate(self, features: Sequence[Mapping[str, Any]], protected: Sequence[Mapping[str, Any]], groups: Mapping[str, Sequence[str]]) -> ProxyGateReport: ...

    # --- Layer 4: NBA ---
    def policy_gate(self, customer: CustomerContact, candidates: Sequence[Action], at: dt.datetime) -> GateResult: ...
    def apply_treatment_ladder(self, case: CaseSnapshot, break_probability: float) -> Action: ...
    def score_break_risk(self, features: Mapping[str, Any]) -> float: ...
    def choose_break_model(self, challenger: ModelEval, incumbent: ModelEval) -> str: ...
    def uplift_readiness(self, overlap_share: float, cases_per_action: Mapping[str, int]) -> UpliftGate: ...
    def propose_next_best_action(self, case: CaseSnapshot, at: dt.datetime) -> NbaDecision: ...
    def propose_next_best_action_for_case(self, case_id: str, at: dt.datetime) -> NbaDecision: """Stateful variant over loaded data."""
    def plan_daily_queue(self, decisions: Sequence[NbaDecision], capacity: ChannelCapacity) -> DailyPlan: ...
    def stress_test(self, plan: DailyPlan, capacity: ChannelCapacity, scenario: StressScenario) -> StressResult: ...
    def label_promise(self, promise: PromiseOutcome, ops_events: Sequence[OpsEvent], as_of: dt.date) -> int | None: ...
    def check_promise(self, draft: PromiseDraft, payroll: PayrollInfo, case: CaseSnapshot) -> PromiseCheck: ...
    def create_approval_batch(self, decisions: Sequence[NbaDecision]) -> ApprovalBatch: ...

    # --- Layer 4: hardship and assist ---
    def hardship_transition(self, current: HardshipState, to: HardshipLevel, actor: Actor, reason: str | None = None, program_id: str | None = None, source: str | None = None) -> HardshipTransitionResult: ...
    def get_hardship_state(self, golden_id: str) -> HardshipState: ...
    def check_eligibility(self, applicant: EligibilityInput, program: HardshipProgram) -> EligibilityResult: ...
    def simulate_plan(self, request: PlanRequest) -> PlanScenario: ...
    def review_board(self, customers: Sequence[Mapping[str, Any]], as_of: dt.date) -> list[ReviewBoardRow]: ...
    def missed_offers(self, cases: Sequence[Mapping[str, Any]], offers: Sequence[Mapping[str, Any]]) -> MissedOfferReport: ...

    # --- Layer 4: post-call summary ---
    def draft_post_call_summary(self, transcript: Transcript, recorded_promise: RecordedPromise | None = None) -> SummaryDraft: ...
    def approve_post_call_summary(self, draft: SummaryDraft, approver: Actor, edits: Mapping[str, Any] | None = None) -> ApprovedSummary: ...

    # --- Governance observability ---
    def audit_log(self, event_type: str | None = None, subject_id: str | None = None) -> list[AuditRecord]: ...
    def llm_request_log(self) -> list[LlmRequest]: ...


class SpecAdapterBase:
    """Convenience base: every operation raises NotImplementedError (=> tests skip).

    Subclass this in ``adapter_impl.py`` and override what your system supports.
    """

    def _ni(self, name: str):
        raise NotImplementedError(f"adapter operation '{name}' is not bound")

    def reset(self) -> None:
        # Default: nothing to reset. Override if your system keeps state between tests.
        return None

    def load_sources(self, tables): self._ni("load_sources")
    def run_pipeline(self, as_of): self._ni("run_pipeline")
    def system_client(self): self._ni("system_client")
    def resolve_identities(self, records, previous=None): self._ni("resolve_identities")
    def find_golden_id(self, source_system, source_key): self._ni("find_golden_id")
    def get_golden_record(self, golden_id): self._ni("get_golden_record")
    def run_quality_rules(self, snapshot, now): self._ni("run_quality_rules")
    def get_data_contract(self, product): self._ni("get_data_contract")
    def detect_schema_drift(self, table, baseline_batch, new_batch): self._ni("detect_schema_drift")
    def find_outage_victims(self, event, repayments): self._ni("find_outage_victims")
    def parse_question(self, question, user): self._ni("parse_question")
    def ask(self, question, user, token_overrides=None): self._ni("ask")
    def validate_sql(self, sql, user): self._ni("validate_sql")
    def suppress_small_groups(self, rows, count_field): self._ni("suppress_small_groups")
    def load_reference_documents(self, docs): self._ni("load_reference_documents")
    def answer_policy_question(self, query, user): self._ni("answer_policy_question")
    def strategy_scorecard(self, cases): self._ni("strategy_scorecard")
    def cure_rate_30d(self, cases): self._ni("cure_rate_30d")
    def employer_radar(self, observations, ops_events=()): self._ni("employer_radar")
    def weather_map(self, observations): self._ni("weather_map")
    def get_feature_registry(self): self._ni("get_feature_registry")
    def get_features_online(self, entity_id, names): self._ni("get_features_online")
    def get_features_offline(self, entity_id, as_of, names): self._ni("get_features_offline")
    def run_parity_check(self, sample_size): self._ni("run_parity_check")
    def proxy_feature_gate(self, features, protected, groups): self._ni("proxy_feature_gate")
    def policy_gate(self, customer, candidates, at): self._ni("policy_gate")
    def apply_treatment_ladder(self, case, break_probability): self._ni("apply_treatment_ladder")
    def score_break_risk(self, features): self._ni("score_break_risk")
    def choose_break_model(self, challenger, incumbent): self._ni("choose_break_model")
    def uplift_readiness(self, overlap_share, cases_per_action): self._ni("uplift_readiness")
    def propose_next_best_action(self, case, at): self._ni("propose_next_best_action")
    def propose_next_best_action_for_case(self, case_id, at): self._ni("propose_next_best_action_for_case")
    def plan_daily_queue(self, decisions, capacity): self._ni("plan_daily_queue")
    def stress_test(self, plan, capacity, scenario): self._ni("stress_test")
    def label_promise(self, promise, ops_events, as_of): self._ni("label_promise")
    def check_promise(self, draft, payroll, case): self._ni("check_promise")
    def create_approval_batch(self, decisions): self._ni("create_approval_batch")
    def hardship_transition(self, current, to, actor, reason=None, program_id=None, source=None): self._ni("hardship_transition")
    def get_hardship_state(self, golden_id): self._ni("get_hardship_state")
    def check_eligibility(self, applicant, program): self._ni("check_eligibility")
    def simulate_plan(self, request): self._ni("simulate_plan")
    def review_board(self, customers, as_of): self._ni("review_board")
    def missed_offers(self, cases, offers): self._ni("missed_offers")
    def draft_post_call_summary(self, transcript, recorded_promise=None): self._ni("draft_post_call_summary")
    def approve_post_call_summary(self, draft, approver, edits=None): self._ni("approve_post_call_summary")
    def audit_log(self, event_type=None, subject_id=None): self._ni("audit_log")
    def llm_request_log(self): self._ni("llm_request_log")


# ---------------------------------------------------------------------------
# System client (system tests: persona journeys)
# ---------------------------------------------------------------------------
@runtime_checkable
class Session(Protocol):
    """A signed-in person. Every method is subject to role-based access control."""

    user_id: str
    role: Role

    # agent workspace
    def work_queue(self) -> list[QueueItem]: ...
    def find_customer(self, source_system: str, source_key: str) -> str | None: ...
    def open_customer(self, golden_id: str) -> CustomerView: ...
    def approve_action(self, decision_id: str, note: str | None = None) -> ActionResult: ...
    def override_action(self, decision_id: str, new_action: Action, reason: str) -> ActionResult: ...
    def check_promise(self, case_id: str, amount: float, due_date: dt.date) -> PromiseCheck: ...
    def record_promise(self, case_id: str, amount: float, due_date: dt.date) -> ActionResult: ...
    def post_call_summary(self, contact_id: str) -> SummaryDraft: ...
    def approve_post_call_summary(self, draft_id: str, edits: Mapping[str, Any] | None = None) -> ActionResult: ...
    def ask_policy(self, query: PolicyQuery) -> PolicyAnswer: ...
    # hardship workbench
    def eligibility(self, golden_id: str) -> list[EligibilityResult]: ...
    def simulate_plan(self, case_id: str, program_id: str, levers: PlanLevers) -> PlanScenario: ...
    def submit_plan_offer(self, scenario_id: str) -> ActionResult: ...
    def approve_plan_offer(self, offer_id: str) -> ActionResult: ...
    def set_hardship_flag(self, golden_id: str, level: HardshipLevel, reason: str | None = None, program_id: str | None = None) -> ActionResult: ...
    def review_board(self) -> list[ReviewBoardRow]: ...
    def missed_offers(self) -> MissedOfferReport: ...
    # team lead
    def list_batches(self) -> list[ApprovalBatch]: ...
    def mark_sample_reviewed(self, batch_id: str) -> ActionResult: ...
    def approve_batch(self, batch_id: str) -> ActionResult: ...
    def stop_batch_item(self, batch_id: str, item_id: str, reason: str) -> ActionResult: ...
    def playbook_proposals(self) -> list[ProposedAction]: ...
    def approve_proposal(self, proposal_id: str) -> ActionResult: ...
    def run_stress_test(self, scenario: StressScenario) -> StressResult: ...
    def monitoring(self) -> MonitoringSnapshot: ...
    # analyst
    def ask(self, question: str, token_overrides: QuestionTokens | None = None) -> AskAnswer: ...
    def employer_radar(self) -> list[RadarRow]: ...
    def weather_map(self) -> MapResult: ...
    def strategy_scorecard(self) -> list[ScorecardRow]: ...
    # data steward
    def identity_review_queue(self) -> list[IdentityReviewItem]: ...
    def decide_identity_review(self, item_id: str, link: bool, reason: str) -> ActionResult: ...
    def data_quality_report(self) -> QualityReport: ...
    def drift_fixes(self) -> list[ProposedFix]: ...
    def approve_drift_fix(self, fix_id: str) -> ActionResult: ...
    # governance
    def audit_log(self, event_type: str | None = None, subject_id: str | None = None) -> list[AuditRecord]: ...
    def delete_audit_record(self, audit_id: str) -> ActionResult: ...


@runtime_checkable
class SystemClient(Protocol):
    """Drives whole journeys. Seed and nightly run are test-harness operations."""

    def seed(self, tables: Mapping[str, list[dict[str, Any]]]) -> None: ...
    def run_nightly(self, as_of: dt.datetime) -> None: ...
    def login(self, user_id: str, role: Role, team_id: str | None = None) -> Session: ...
    def outbound_messages(self) -> list[OutboundMessage]: ...
    def dispatch_due(self, now: dt.datetime) -> list[OutboundMessage]: """Run the sender for anything approved and due."""
