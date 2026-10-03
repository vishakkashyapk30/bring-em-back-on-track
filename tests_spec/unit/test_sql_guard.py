"""SQL checker for natural-language answers (V1 §4 step 3; v2 §4 step 4)."""

from __future__ import annotations

import re

import pytest

from tests_spec import spec_constants as C

pytestmark = pytest.mark.sql_guard

GOOD_SQL = (
    "SELECT p.ptp_id, s.score FROM gold.promises_to_pay p "
    "JOIN gold.model_scores s ON s.entity_id = p.ptp_id "
    "WHERE s.model_name = 'ptp_break' AND p.ptp_status = 'open' ORDER BY s.score DESC LIMIT 50"
)


def test_allowlisted_read_only_query_passes(adapter, analyst_user):
    """V1 §4 step 3: a query that only reads, uses allowed columns and has a row limit passes.
    The Brief "Collections Ask" mock-up SQL joins gold.promises_to_pay and gold.model_scores."""
    res = adapter.validate_sql(GOOD_SQL, analyst_user)
    assert res.ok, res.violations


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO gold.audit_log VALUES (1)",
        "UPDATE gold.c360_customer SET hardship_flag = 'none'",
        "DELETE FROM gold.promises_to_pay",
        "DROP TABLE gold.c360_customer",
        "TRUNCATE gold.nba_decisions",
        "CREATE TABLE x AS SELECT 1",
        "ALTER TABLE gold.c360_customer ADD COLUMN y INT",
        "MERGE INTO gold.c360_customer t USING s ON t.golden_id = s.golden_id WHEN MATCHED THEN DELETE",
        "GRANT SELECT ON gold.c360_customer TO public",
        "COPY gold.c360_customer TO '/tmp/out.csv'",
        "ATTACH 'other.db' AS other",
        "SELECT 1 LIMIT 1; DROP TABLE gold.c360_customer",
        "WITH d AS (DELETE FROM gold.promises_to_pay RETURNING *) SELECT * FROM d LIMIT 5",
        "SELECT 1 LIMIT 1 /* harmless */; UPDATE gold.c360_customer SET consent_call = true",
    ],
)
def test_anything_but_a_single_read_is_rejected(adapter, analyst_user, sql):
    """V1 §4 step 3: "makes sure the query only reads data"; v2: "sqlglot allows SELECT only ... on a
    read-only connection"; NI S5: "Ask is read-only"."""
    res = adapter.validate_sql(sql, analyst_user)
    assert not res.ok


@pytest.mark.fairness
@pytest.mark.parametrize("col", C.ALL_EXCLUDED_FROM_DECISIONS)
def test_protected_attribute_columns_are_never_allowed(adapter, analyst_user, col):
    """V1 §4 step 2: "Personal details and protected attributes are simply not in the dictionary, so
    nobody can ask for them"; V1 §10."""
    for sql in (
        f"SELECT {col}, COUNT(*) FROM gold.c360_customer GROUP BY {col} LIMIT 100",
        f"SELECT COUNT(*) FROM gold.c360_customer WHERE {col} IS NOT NULL LIMIT 100",
    ):
        res = adapter.validate_sql(sql, analyst_user)
        assert not res.ok, sql


@pytest.mark.parametrize("col", ["national_id_hash", "primary_phone_e164", "email", "date_of_birth", "first_name"])
def test_direct_pii_columns_are_not_allowed_for_analysts(adapter, analyst_user, col):
    """V1 §4 step 2 (personal details not in the dictionary); V1 §10 masking for analysts; contract
    Not allowed "Exporting direct PII outside the restricted zone"."""
    res = adapter.validate_sql(f"SELECT {col} FROM gold.c360_customer LIMIT 10", analyst_user)
    assert not res.ok


def test_unknown_table_is_rejected(adapter, analyst_user):
    """V1 §4 step 3 "uses allowed columns": a table outside the semantic layer is not allowed."""
    res = adapter.validate_sql("SELECT * FROM raw.customers_bronze LIMIT 10", analyst_user)
    assert not res.ok


def test_query_without_limit_is_rejected_or_limited(adapter, analyst_user):
    """V1 §4 step 3: the checker makes sure the query "has a row limit"."""
    res = adapter.validate_sql("SELECT ptp_id FROM gold.promises_to_pay WHERE ptp_status = 'open'", analyst_user)
    if res.ok:
        assert res.effective_row_limit is not None
        assert res.final_sql and re.search(r"\blimit\b", res.final_sql, re.I)
    else:
        assert any("limit" in v.lower() for v in res.violations)


def test_row_limit_has_a_ceiling(adapter, analyst_user):
    """V1 §4 step 3 row limit; the maximum is TBC (MAX_SQL_ROW_LIMIT)."""
    cap = C.require_constant(C.MAX_SQL_ROW_LIMIT, "MAX_SQL_ROW_LIMIT")
    res = adapter.validate_sql(f"SELECT ptp_id FROM gold.promises_to_pay LIMIT {cap * 100}", analyst_user)
    assert (not res.ok) or (res.effective_row_limit is not None and res.effective_row_limit <= cap)


def test_select_star_policy(adapter, analyst_user):
    """V1 §4 step 3 "uses allowed columns": SELECT * either refused or expanded to allowed columns (TBC)."""
    refused = C.require_constant(C.SELECT_STAR_REFUSED, "SELECT_STAR_REFUSED")
    res = adapter.validate_sql("SELECT * FROM gold.c360_customer LIMIT 10", analyst_user)
    assert (not res.ok) is refused


def test_role_row_filter_is_applied_for_agents(adapter, agent_user):
    """V1 §4 step 3: the checker "applies the user's row filter"; v2 §4 RAG: "Agents see their own
    cases (assigned_agent_id)"."""
    res = adapter.validate_sql(
        "SELECT case_id FROM gold.collections_cases WHERE case_status = 'open' LIMIT 20", agent_user
    )
    assert res.ok
    assert res.row_filter_applied
    assert agent_user.user_id in (res.final_sql or "")


def test_agent_cannot_remove_their_row_filter(adapter, agent_user):
    """V1 §4 step 3 + V1 §10 row filters: an OR 1=1 trick or a filter on another agent must not
    widen the agent's rows."""
    res = adapter.validate_sql(
        "SELECT case_id FROM gold.collections_cases WHERE assigned_agent_id = 'agent-002' OR 1=1 LIMIT 20",
        agent_user,
    )
    if res.ok:
        assert res.row_filter_applied and agent_user.user_id in (res.final_sql or "")
