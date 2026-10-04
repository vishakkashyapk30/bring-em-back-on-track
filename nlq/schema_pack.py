"""The curated schema a language model may see when it writes SQL for Ask (nlq/llm_sql.py).

Only what an analyst or team lead may query: the typed silver tables the certified metrics already use, a curated set
of their columns with one-line descriptions (from the data dictionary, read-only), the join keys, the certified metric
formulas as hints, small value lists for enum columns (read live from the warehouse), the as_of date and the default
filters the certified definitions apply. Protected attributes (common/protected.py), direct-identifier columns
(nlq/executor.PII_COLUMNS) and every column the dictionary marks as personal or protected are left out, so the model
cannot even see them. Every column of a pack table that is not in the pack is "hidden": the SQL check in llm_sql
rejects any query that names one.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from functools import lru_cache

from common.config import ROOT
from common.protected import FORBIDDEN, assert_no_protected
from nlq.executor import ALLOWED, PII_COLUMNS

DICTIONARY = ROOT / "docs" / "data_dictionary" / "CIBC Hackathon - Data Dictionary - Columns.csv"
# Dictionary sensitivities that keep a column out of the pack (quasi-identifiers are left out too, except the
# province, which the certified metrics already break down by).
SENSITIVE = {"direct pii", "protected attribute", "quasi-identifier"}
KEEP_QUASI = {"province_code"}


@dataclass(frozen=True)
class TableSpec:
    description: str
    grain: str
    columns: tuple[str, ...]
    notes: tuple[str, ...] = ()
    reference: bool = False   # a reference table (not about customers): rows may be listed without aggregating


TABLES: dict[str, TableSpec] = {
    "collections_cases": TableSpec(
        "Collections cases: bucket, queue, strategy, promises, hardship, cure and outcome.",
        "one row per case (open and closed)",
        ("case_id", "case_open_date", "case_open_reason", "case_status", "primary_product", "entry_dpd", "current_dpd",
         "current_bucket", "prior_bucket", "total_overdue", "total_exposure", "entry_overdue", "queue", "assigned_team",
         "assigned_agent_id", "language_of_service", "strategy_code", "test_cell", "assignment_method",
         "contact_attempts_total", "rpc_count", "promises_total", "promises_kept", "promises_broken", "promises_open",
         "payments_since_open_amount", "cure_flag", "cure_date", "days_to_cure", "recidivism_flag", "prior_cases_12m",
         "hardship_flag", "hardship_program_offered", "hardship_program_accepted", "hardship_plan_type",
         "payment_plan_flag", "settlement_offered_flag", "dispute_flag", "dispute_type", "complaint_flag",
         "cease_contact_flag", "third_party_rep_flag", "insolvency_hold_flag", "deceased_hold_flag",
         "agency_placement_flag", "legal_referral_flag", "chargeoff_flag", "chargeoff_amount", "province_code",
         "days_in_collections", "cost_to_collect_est", "expected_loss_est", "escalation_flag", "outcome",
         "outcome_date",
         "roll_forward_count", "roll_back_count", "nba_accepted_flag"),
        ("An OPEN case is outcome IS NULL (case_status has several open values; do not use case_status = 'open').",
         "Cure rate (certified): share of cases with cure_flag AND days_to_cure <= 30, excluding insolvency_hold_flag "
         "and deceased_hold_flag cases; period by case_open_date.")),
    "promises_to_pay": TableSpec(
        "Promises to pay made on cases: amount, due date, status, amount paid.",
        "one row per promise",
        ("ptp_id", "case_id", "product", "agent_id", "ptp_channel", "ptp_created_ts", "ptp_amount", "ptp_due_date",
         "ptp_type", "ptp_sequence_in_case", "prior_broken_ptp_count", "overdue_at_creation", "dpd_at_creation",
         "payment_method_promised", "reminder_scheduled_flag", "grace_days", "ptp_status", "amount_paid_against",
         "paid_date", "broken_reason_agent_coded"),
        ("Promise kept or broken rates are over RESOLVED promises only: ptp_status IN ('kept', 'partially_kept', "
         "'broken') (open and cancelled are excluded); the period is ptp_due_date.",
         "agent_id is NULL for self-serve promises.")),
    "contact_history": TableSpec(
        "Every contact attempt and system event: channel, time, result, promise taken, cost.",
        "one row per contact attempt or system event (about 2.7 million rows)",
        ("contact_id", "case_id", "agent_id", "strategy_code", "test_cell", "treatment_code", "direction", "channel",
         "channel_v2", "contact_ts_local", "day_of_week", "contact_hour_local", "stat_holiday_flag",
         "within_permitted_hours_flag", "attempt_number_case", "dial_result", "talk_duration_sec", "abandoned_flag",
         "rpc_flag", "third_party_contact_flag", "language_used", "outcome_code", "ptp_made_flag", "ptp_id",
         "payment_taken_flag", "payment_amount", "dispute_raised_flag", "complaint_raised_flag",
         "hardship_mentioned_flag", "cease_request_flag", "callback_requested_flag", "sms_delivered_flag",
         "link_clicked_flag", "link_payment_flag", "email_opened_flag", "contact_cost_cad", "system_event_type",
         "ops_incident_id", "dpd_at_contact", "bucket_at_contact", "agent_site"),
        ("The channel is coalesce(channel_v2, channel) (the column was renamed on 26 Sep 2026; use both).",
         "Rows with channel 'system' are internal events, not contacts: exclude them when counting contacts.",
         "Outbound call attempts: coalesce(channel_v2, channel) = 'call' AND direction = 'outbound'.",
         "The period is contact_ts_local (a TIMESTAMP: compare with CAST(contact_ts_local AS DATE)).")),
    "agents": TableSpec(
        "Agent roster: site, team, role, tenure, capacity and 90-day performance.",
        "one row per agent",
        ("agent_id", "site", "team_id", "team_lead_id", "role", "employment_type", "tenure_months",
         "vulnerable_customer_certified", "shift_pattern", "fte", "max_concurrent_cases", "current_case_load",
         "rpc_rate_90d", "ptp_rate_90d", "ptp_kept_rate_90d", "cure_rate_90d", "avg_handle_time_sec",
         "qa_score_avg_90d", "complaints_90d", "coaching_flag", "status"),
        ("The *_rate_90d columns are fractions between 0 and 1.",), reference=True),
    "card_accounts": TableSpec(
        "Credit card accounts: product, limit, balance, utilisation, days past due, status, charge-off.",
        "one row per card account at its latest snapshot (accounts still on book have snapshot_date = as_of date)",
        ("card_account_id", "snapshot_date", "product_code", "card_tier", "account_status", "credit_limit",
         "current_balance", "utilisation", "past_due_amount", "minimum_payment_due", "dpd", "dpd_bucket",
         "months_on_book", "autopay_enrolled", "overlimit_flag", "hardship_program_flag", "chargeoff_flag",
         "chargeoff_date", "chargeoff_amount"),
        ("Card delinquency (certified): share with dpd >= 1 among snapshot_date = as_of date AND account_status IN "
         "('active', 'blocked') AND dpd IS NOT NULL.",)),
    "loan_accounts": TableSpec(
        "Personal loans, auto loans, mortgages and lines of credit: balance, days past due, hardship, charge-off.",
        "one row per loan at its latest snapshot (loans still on book have snapshot_date = as_of date)",
        ("loan_id", "snapshot_date", "product_type", "product_code", "secured_flag", "origination_date",
         "original_amount", "interest_rate", "principal_balance", "total_outstanding", "past_due_amount",
         "missed_payments_count", "dpd", "dpd_bucket", "pad_enrolled", "hardship_program_flag", "restructure_flag",
         "chargeoff_flag", "chargeoff_date", "chargeoff_amount"),
        ("Loan delinquency (certified): share with dpd >= 1 among snapshot_date = as_of date AND NOT "
         "coalesce(chargeoff_flag, false) AND dpd IS NOT NULL.",)),
    "deposit_accounts": TableSpec(
        "Chequing, savings, TFSA and USD accounts: balances, overdraft, payroll signals.",
        "one row per deposit account at its latest snapshot",
        ("deposit_account_id", "snapshot_date", "product_type", "account_status", "current_balance",
         "overdraft_limit", "overdraft_used", "nsf_count_mtd", "payroll_deposit_flag", "payroll_frequency_detected",
         "payroll_delay_days", "ei_deposit_flag", "high_cost_lender_txn_flag", "garnishment_flag"),
        ("Payroll delay share (certified): share with payroll_delay_days > 7 among payroll_deposit_flag accounts.",)),
    "account_monthly_snapshot": TableSpec(
        "Quarter-end history of every account across products (used for roll rates).",
        "one row per account per quarter-end (about 12.5 million rows)",
        ("account_id", "month_end_date", "product_type", "account_status", "balance", "dpd", "dpd_bucket",
         "write_off_flag"),
        ("month_end_date is TEXT in mixed formats: parse it with coalesce(try_strptime(month_end_date, '%Y-%m-%d'), "
         "try_strptime(month_end_date, '%d/%m/%Y'), try_strptime(month_end_date, '%Y%m%d'))::DATE.",
         "Quarter-ends available: 2023-12-31 to 2026-06-30. Exclude rows with dpd IS NULL.")),
    "case_assignment_history": TableSpec(
        "Which agent, team and queue held each case, how it was assigned, and what happened during it.",
        "one row per assignment",
        ("case_id", "agent_id", "team_id", "queue", "assigned_ts", "unassigned_ts", "assignment_reason",
         "assignment_method", "continuity_flag", "language_match_flag", "certified_for_vulnerable_flag",
         "dpd_at_assignment", "contacts_during", "rpcs_during", "ptps_during", "payments_during_amount",
         "complaint_during_flag"),
        ("assignment_method = 'randomised_pilot' marks the randomised pilot.",)),
    "offers": TableSpec(
        "Hardship and treatment offers made on cases and the customer's response.",
        "one row per offer",
        ("offer_id", "case_id", "program_id", "offer_ts", "offered_by", "nba_recommended_flag", "eligibility_result",
         "proposed_payment_amount", "duration_months", "customer_response", "decline_reason", "plan_start_date",
         "plan_status", "plan_payments_due", "plan_payments_made")),
    "hardship_programs": TableSpec(
        "Hardship programme rules: eligibility limits and payment relief.",
        "one row per programme version",
        ("program_id", "version", "program_name", "product_types", "max_dpd", "min_months_on_book", "max_uses_12m",
         "payment_reduction_pct", "duration_months", "fees_waived_flag", "approver_level", "effective_from",
         "effective_to"),
        ("The current version has effective_to = DATE '9999-12-31'.",), reference=True),
    "model_scores": TableSpec(
        "The bank's existing model scores (risk, promise-break probability, cure, contact timing).",
        "one row per score (about 1.7 million rows; score_date has four values)",
        ("score_date", "model_name", "model_version", "entity_type", "case_id", "ptp_id", "score", "score_band",
         "risk_grade", "threshold_used", "recommended_action"),
        ("Use score_date = as_of date for current scores. Scores are model estimates, not outcomes.",)),
    "ops_events": TableSpec(
        "Incidents, outages, releases and policy changes with their time window.",
        "one row per event",
        ("event_id", "event_type", "system", "start_ts", "end_ts", "severity", "description",
         "affected_customers_est"), reference=True),
    "channel_capacity": TableSpec(
        "Daily channel capacity, usage and unit cost by time band.",
        "one row per date, channel and time band",
        ("date", "channel", "time_band", "capacity_units", "capacity_unit_type", "used_units", "unit_cost_cad",
         "daily_budget_cad", "outage_flag"), reference=True),
}

# Small value lists shown to the model (read from the warehouse, at most 25 values each).
ENUMS: dict[str, tuple[str, ...]] = {
    "collections_cases": ("case_open_reason", "case_status", "primary_product", "current_bucket", "queue",
                          "language_of_service", "strategy_code", "test_cell", "assignment_method",
                          "hardship_plan_type",
                          "dispute_type", "outcome", "province_code"),
    "promises_to_pay": ("product", "ptp_channel", "ptp_type", "payment_method_promised", "ptp_status",
                        "broken_reason_agent_coded"),
    "contact_history": ("direction", "channel", "channel_v2", "dial_result", "outcome_code", "agent_site",
                        "day_of_week", "system_event_type"),
    "agents": ("site", "role", "employment_type", "shift_pattern", "status"),
    "card_accounts": ("product_code", "card_tier", "account_status", "dpd_bucket"),
    "loan_accounts": ("product_type", "dpd_bucket"),
    "deposit_accounts": ("product_type", "account_status", "payroll_frequency_detected"),
    "account_monthly_snapshot": ("product_type", "dpd_bucket"),
    "case_assignment_history": ("assignment_reason", "assignment_method"),
    "offers": ("offered_by", "eligibility_result", "customer_response", "decline_reason", "plan_status"),
    "model_scores": ("model_name", "entity_type", "score_band"),
    "ops_events": ("event_type", "severity"),
    "channel_capacity": ("channel", "time_band"),
}

JOINS = (
    "promises_to_pay.case_id = collections_cases.case_id",
    "contact_history.case_id = collections_cases.case_id",
    "contact_history.ptp_id = promises_to_pay.ptp_id",
    "offers.case_id = collections_cases.case_id",
    "offers.program_id = hardship_programs.program_id",
    "case_assignment_history.case_id = collections_cases.case_id",
    "model_scores.case_id = collections_cases.case_id (and model_scores.ptp_id = promises_to_pay.ptp_id)",
    "agents.agent_id = collections_cases.assigned_agent_id / promises_to_pay.agent_id / contact_history.agent_id",
    "collections_cases.primary_product uses card / personal_loan / auto_loan / loc / overdraft / mortgage; "
    "loan_accounts.product_type uses personal_loan / auto_loan / mortgage / unsecured_loc / student_loc",
)

RULES = (
    "Today (the as_of date) is {as_of}. 'Today', 'current' and 'now' mean that date; 'last month' is the calendar "
    "month before it; years without a date mean that calendar year.",
    "Rates are percentages: round(100.0 * avg(CASE WHEN <condition> THEN 1 ELSE 0 END), 1) AS <name>_pct, and put "
    "the count of the base next to every rate.",
    "Money is CAD; round amounts to 2 decimals.",
    "Ask returns aggregates: never output case, promise, contact, account or customer identifiers row by row.",
)

EXAMPLES = (
    ("What is the average talk time of answered outbound calls by agent site in September 2026?",
     "SELECT h.agent_site, round(avg(h.talk_duration_sec), 1) AS avg_talk_sec, count(*) AS calls "
     "FROM contact_history h WHERE coalesce(h.channel_v2, h.channel) = 'call' AND h.direction = 'outbound' "
     "AND h.dial_result = 'answered' AND CAST(h.contact_ts_local AS DATE) BETWEEN DATE '2026-09-01' AND "
     "DATE '2026-09-30' GROUP BY 1 ORDER BY 2 DESC"),
    ("Which three strategies have the highest share of open cases with a broken promise?",
     "SELECT c.strategy_code, round(100.0 * avg(CASE WHEN c.promises_broken > 0 THEN 1 ELSE 0 END), 1) "
     "AS with_broken_promise_pct, count(*) AS open_cases FROM collections_cases c WHERE c.outcome IS NULL "
     "GROUP BY 1 ORDER BY 2 DESC LIMIT 3"),
    ("How many hardship offers were accepted per programme in 2026?",
     "SELECT o.program_id, count(*) FILTER (WHERE o.customer_response = 'accepted') AS accepted, count(*) AS offers "
     "FROM offers o WHERE year(o.offer_ts) = 2026 GROUP BY 1 ORDER BY 2 DESC"),
)


def _dictionary() -> dict[tuple[str, str], tuple[str, str]]:
    """(table, column) -> (description, sensitivity) from the data dictionary (read-only)."""
    out: dict[tuple[str, str], tuple[str, str]] = {}
    if DICTIONARY.exists():
        with DICTIONARY.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                out[(r["Table"], r["Column"])] = (r["Description"].strip(), r["Sensitivity"].strip().lower())
    return out


def blocked_columns() -> set[str]:
    """Columns that must never reach the model: protected attributes, direct identifiers and anything the dictionary
    marks personal or protected (bare names, lower case)."""
    dd = _dictionary()
    marked = {col.lower() for (_t, col), (_d, sens) in dd.items() if sens in SENSITIVE} - KEEP_QUASI
    return {c.lower() for c in FORBIDDEN} | {c.lower() for c in PII_COLUMNS} | marked


def _check_curated() -> None:
    bad = {f"{t}.{c}" for t, spec in TABLES.items() for c in spec.columns if c.lower() in blocked_columns()}
    assert_no_protected([c.split(".")[-1] for c in bad], "schema pack")
    if bad:
        raise ValueError(f"schema pack lists personal or protected columns: {sorted(bad)}")
    missing = set(TABLES) - ALLOWED
    if missing:
        raise ValueError(f"schema pack tables not allowed for Ask: {sorted(missing)}")


@dataclass(frozen=True)
class Pack:
    as_of: date
    tables: dict[str, TableSpec]
    columns: dict[str, dict[str, tuple[str, str]]]   # table -> column -> (type, description)
    values: dict[tuple[str, str], tuple[str, ...]]
    hidden: frozenset[str]                            # real columns of pack tables that are NOT in the pack

    @property
    def visible(self) -> frozenset[str]:
        return frozenset(c for cols in self.columns.values() for c in cols)

    def text(self) -> str:
        return render(self)


def tables_for_role(role: str | None) -> tuple[str, ...]:
    """Agents get nothing (they never reach the SQL path); analysts, team leads and batch jobs get the curated tables.
    Never wider than the executor's ALLOWED set."""
    if role == "agent":
        return ()
    return tuple(t for t in TABLES if t in ALLOWED)


@lru_cache(maxsize=8)
def build(as_of: date, role: str | None = None) -> Pack:
    """Read column types, row counts and enum values from the read-only warehouse; descriptions from the dictionary."""
    from common.db import warehouse

    _check_curated()
    dd = _dictionary()
    names = tables_for_role(role)
    con = warehouse(read_only=True)
    try:
        con.execute("SET search_path = 'silver,gold'")
        columns: dict[str, dict[str, tuple[str, str]]] = {}
        hidden: set[str] = set()
        values: dict[tuple[str, str], tuple[str, ...]] = {}
        for t in names:
            real = dict(con.execute("SELECT column_name, data_type FROM information_schema.columns "
                                    "WHERE table_schema = 'silver' AND table_name = ?", [t]).fetchall())
            spec = TABLES[t]
            columns[t] = {c: (real[c], DESCRIPTIONS.get((t, c)) or dd.get((t, c), ("", ""))[0])
                          for c in spec.columns if c in real}
            hidden |= {c.lower() for c in real} - {c.lower() for c in spec.columns}
            for c in ENUMS.get(t, ()):
                if c in columns[t]:
                    rows = con.execute(f'SELECT DISTINCT "{c}" FROM {t} WHERE "{c}" IS NOT NULL ORDER BY 1 '
                                       "LIMIT 26").fetchall()
                    if len(rows) <= 25:
                        values[(t, c)] = tuple(str(r[0]) for r in rows)
    finally:
        con.close()
    visible = {c.lower() for cols in columns.values() for c in cols}
    return Pack(as_of, {t: TABLES[t] for t in names}, columns, values, frozenset(hidden - visible))


# Where the dictionary's wording is too terse or misleading for writing SQL.
DESCRIPTIONS: dict[tuple[str, str], str] = {
    ("collections_cases", "outcome"): "Final outcome: cured / settled / charged_off; NULL while the case is open",
    ("collections_cases", "current_dpd"): "Days past due today (max across the case's accounts)",
    ("collections_cases", "total_overdue"): "Amount past due across the case (CAD)",
    ("collections_cases", "queue"): "Work queue",
    ("collections_cases", "current_bucket"): "Days-past-due bucket today",
    ("contact_history", "channel_v2"): "Channel after the 26 Sep 2026 rename (NULL before); use coalesce(channel_v2, "
                                       "channel)",
    ("contact_history", "agent_site"): "Site of the agent who made the contact (NULL for automated contacts)",
    ("card_accounts", "product_code"): "Card product code",
    ("account_monthly_snapshot", "month_end_date"): "Quarter-end date as TEXT in mixed formats (parse it, see notes)",
}


def certified_hints(as_of: date) -> list[str]:
    """The certified metric formulas (semantic/registry.py) as one line each: the model should reuse them."""
    from semantic.registry import METRICS

    out = []
    for m in METRICS:
        where = " AND ".join(w.replace("{as_of}", str(as_of)) for w in m.where) or "(none)"
        select = m.select.replace("{cure_days}", "30")
        out.append(f"{m.id}: SELECT {select} FROM {m.base} WHERE {where}"
                   + (f"; period column {m.time_col}" if m.time_col else ""))
    return out


SHORT_TYPES = {"VARCHAR": "text", "BIGINT": "int", "INTEGER": "int", "DOUBLE": "num", "BOOLEAN": "bool",
               "TIMESTAMP": "timestamp", "DATE": "date"}


def _describe(desc: str, vals: tuple[str, ...] | None) -> str:
    """Short description; one that only lists values ('a / b / c') is replaced by the real value list."""
    if vals and " / " in desc:
        desc = ""
    desc = desc if len(desc) <= 80 else desc[:77].rstrip() + "..."
    return (f": {desc}" if desc else "") + (f" [values: {', '.join(vals)}]" if vals else "")


def render(pack: Pack) -> str:
    """The pack as compact text for the prompt (small local models have a short context)."""
    lines = [f"DuckDB dialect. Unqualified table names. as_of date: {pack.as_of}."]
    for t, spec in pack.tables.items():
        lines.append(f"\nTABLE {t}: {spec.description} Grain: {spec.grain}.")
        for c, (typ, desc) in pack.columns[t].items():
            lines.append(f"  {c} {SHORT_TYPES.get(typ, typ.lower())}" + _describe(desc, pack.values.get((t, c))))
        lines += [f"  NOTE: {n}" for n in spec.notes]
    lines.append("\nJOIN KEYS:")
    lines += [f"  {j}" for j in JOINS]
    lines.append("\nCERTIFIED METRIC FORMULAS (reuse these definitions and their default filters):")
    lines += [f"  {h}" for h in certified_hints(pack.as_of)]
    lines.append("\nRULES:")
    lines += [f"  {r.format(as_of=pack.as_of)}" for r in RULES]
    lines.append("\nEXAMPLES:")
    for q, sql in EXAMPLES:
        lines += [f"  Q: {q}", f"  SQL: {sql}"]
    return "\n".join(lines)
