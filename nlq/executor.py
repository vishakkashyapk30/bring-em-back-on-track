"""Run guarded SQL on a READ-ONLY warehouse connection (D5). The guard allows only the analyst-safe tables:
typed silver tables without direct identifiers, plus gold role views. Groups with fewer than 10 rows behind them
are suppressed when the result is an aggregate over customers."""

from __future__ import annotations

from typing import Any

from common.config import get_settings
from common.db import warehouse
from nlq.guard import validate

# Silver tables Ask may read (no CRM customer table: it holds names, contact details and protected attributes)
ALLOWED = {
    "promises_to_pay", "collections_cases", "contact_history", "agents", "card_accounts", "loan_accounts",
    "deposit_accounts", "account_monthly_snapshot", "stg_account_snapshot", "offers", "hardship_programs",
    "model_scores", "channel_capacity", "ops_events", "case_assignment_history", "agent_shifts",
    "metric_definitions", "geo_reference", "card_statements", "loan_instalments", "salary_credit_history",
    "c360_case", "role_analyst_metrics_v", "code_lookups", "reference_documents", "qa_checklist",
}
PII_COLUMNS = {"first_name", "last_name", "full_name_raw", "preferred_name", "email", "primary_phone_e164",
               "primary_phone_raw", "address_line1", "address_line2", "cardholder_name_raw", "borrower_name_raw",
               "holder_name_raw", "cardholder_phone_raw", "borrower_phone_raw", "holder_phone_raw",
               "subject_name_reported", "subject_address_reported", "date_of_birth", "dob_raw",
               "cardholder_dob_raw", "borrower_dob_raw", "holder_dob_raw", "cardholder_postal_raw",
               "borrower_postal_raw", "holder_postal_raw", "phone_number_hash"}


def check_columns(sql: str) -> None:
    """Raise PermissionError if the query names a direct-identifier column, or selects `*` / `t.*` (which would
    return the identifier columns of the allowlisted source tables without naming them)."""
    import sqlglot
    from sqlglot import exp

    tree = sqlglot.parse_one(sql, read="duckdb")
    for sel in tree.find_all(exp.Select):
        if any(isinstance(e, exp.Star) or (isinstance(e, exp.Column) and isinstance(e.this, exp.Star))
               for e in sel.expressions):
            raise PermissionError("SELECT * isn't allowed in Ask: name the columns you need")
    cols = {c.name.lower() for c in tree.find_all(exp.Column)}
    if cols & PII_COLUMNS:
        raise PermissionError(f"Direct personal details can't be queried: {sorted(cols & PII_COLUMNS)}")


def execute(sql: str, max_rows: int = 1000,
            row_filters: dict[str, str] | None = None) -> tuple[str, list[str], list[tuple[Any, ...]]]:
    safe = validate(sql, ALLOWED, max_limit=max_rows)
    check_columns(safe)
    if row_filters:
        from nlq.guard import apply_row_filters

        safe, _ = apply_row_filters(safe, row_filters)
    con = warehouse(read_only=True)
    try:
        con.execute("SET search_path = 'silver,gold'")
        rel = con.sql(safe)
        names, rows = rel.columns, rel.fetchall()
    finally:
        con.close()
    return safe, names, _suppress(names, rows)


def _suppress(names: list[str], rows: list[tuple]) -> list[tuple]:
    """Mask count-like columns under the small-group threshold (customers / accounts / cases)."""
    k = get_settings().suppression_min_group
    count_cols = [i for i, n in enumerate(names) if n in ("customers",)]
    if not count_cols:
        return rows
    return [tuple("<10" if (i in count_cols and isinstance(v, int) and v < k) else v for i, v in enumerate(r))
            for r in rows]
