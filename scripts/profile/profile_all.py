"""Profiling of the Maple Bank release (bronze Parquet). Reproduces the numbers behind the build decisions.

Run: `make profile` (needs `make bronze` first). Writes reports/profile/profile.json and docs/profiling_report.md.
Decisions taken from these numbers are recorded in docs/profiling_decisions.md.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import duckdb

from common.config import get_settings

ROOT = Path(__file__).resolve().parents[2]
VALID_CRM = "crm_customer_id IN (SELECT crm_customer_id FROM customers)"

CHECKS: list[tuple[str, str, str]] = [
    # (key, title, sql)  every query returns a small table
    ("row_counts", "Row counts (bronze)", """
        SELECT 'customers' t, count(*) n FROM customers UNION ALL SELECT 'card_accounts', count(*) FROM card_accounts
        UNION ALL SELECT 'loan_accounts', count(*) FROM loan_accounts UNION ALL SELECT 'deposit_accounts', count(*)
        FROM deposit_accounts UNION ALL SELECT 'collections_cases', count(*) FROM collections_cases UNION ALL
        SELECT 'contact_history', count(*) FROM contact_history UNION ALL SELECT 'promises_to_pay', count(*)
        FROM promises_to_pay UNION ALL SELECT 'agent_notes', count(*) FROM agent_notes UNION ALL
        SELECT 'call_transcripts', count(*) FROM call_transcripts UNION ALL SELECT 'external', count(*) FROM external
        UNION ALL SELECT 'account_monthly_snapshot', count(*) FROM account_monthly_snapshot"""),
    ("crm_records", "CRM records: history, deletions, duplicates, national ID", """
        SELECT count(*) records, count(*) FILTER (WHERE effective_to_ts NOT LIKE '9999%') historical,
               count(*) FILTER (WHERE is_deleted = 'true') deleted, count(duplicate_of_crm_id) duplicate_of_set,
               count(national_id_hash) with_national_id, count(DISTINCT national_id_hash) distinct_national_id,
               count(national_id_hash) - count(DISTINCT national_id_hash) repeated_national_id
        FROM customers"""),
    ("accounts", "Accounts per source system (one row per account)", """
        SELECT 'cards' sys, count(*) accounts, count(DISTINCT src_customer_ref) customer_keys, NULL::BIGINT padded_keys,
               NULL::BIGINT short_keys FROM card_accounts
        UNION ALL SELECT 'lending', count(*), count(DISTINCT src_customer_ref), NULL, NULL FROM loan_accounts
        UNION ALL SELECT 'core_banking', count(*), count(DISTINCT src_customer_ref),
               count(DISTINCT lpad(src_customer_ref, 10, '0')), count(*) FILTER (WHERE length(src_customer_ref) < 10)
        FROM deposit_accounts"""),
    ("snapshot_crm_links", "account_monthly_snapshot: CRM IDs per account (valid = exists in customers)", f"""
        WITH a AS (SELECT DISTINCT account_id, crm_customer_id, {VALID_CRM} ok FROM account_monthly_snapshot),
             b AS (SELECT account_id, count(*) n_ids, count(*) FILTER (WHERE ok) n_valid FROM a GROUP BY 1)
        SELECT n_ids, n_valid, count(*) accounts FROM b GROUP BY ALL ORDER BY ALL"""),
    ("snapshot_date_formats", "account_monthly_snapshot.month_end_date formats", """
        SELECT regexp_replace(month_end_date, '[0-9]', '9', 'g') fmt, count(*) n FROM account_monthly_snapshot
        GROUP BY 1 ORDER BY 2 DESC"""),
    ("ops_events", "Operational events", """
        SELECT event_id, event_type, start_ts, end_ts, affected_customers_est, description FROM ops_events"""),
    ("employer_signal", "ECO-0715 check: payroll delay and EI, Windsor-Essex manufacturing vs rest", """
        SELECT CASE WHEN upper(left(replace(holder_postal_raw, ' ', ''), 2)) IN ('N8', 'N9') THEN 'windsor_essex'
                    ELSE 'rest' END region,
               regexp_matches(payroll_descriptor_raw, 'AUTO|PTS|MACHIN|FABRICAT|STEEL|PLANT|MFG|MANUF') manufacturing,
               count(*) n, round(avg((try_cast(payroll_delay_days AS INT) > 7)::INT), 3) payroll_delay_gt7,
               round(avg((ei_deposit_flag = 'true')::INT), 3) ei_share
        FROM deposit_accounts WHERE payroll_descriptor_raw IS NOT NULL GROUP BY ALL ORDER BY ALL"""),
    ("windsor_cases", "Cases opened per month and hardship share, Windsor-Essex vs rest (2026)", """
        SELECT CASE WHEN upper(left(c.fsa, 2)) IN ('N8', 'N9') THEN 'windsor_essex' ELSE 'rest' END region,
               substr(k.case_open_date, 1, 7) open_month, count(*) cases,
               round(avg((k.hardship_flag = 'true')::INT), 3) hardship_share
        FROM collections_cases k JOIN customers c ON c.crm_customer_id = k.coll_customer_ref
        WHERE k.case_open_date >= '2026-04' GROUP BY ALL ORDER BY ALL"""),
    ("hardship_programs", "Hardship programs (current versions)", """
        SELECT program_id, product_types, min_hardship_level, max_dpd, payment_reduction_pct, rate_override,
               duration_months, term_extension_max_months, approver_level
        FROM hardship_programs WHERE effective_to LIKE '9999%' ORDER BY 1"""),
    ("promises", "Promises to pay", """
        SELECT ptp_status, count(*) n, round(avg((customer_stated_income_date IS NOT NULL)::INT), 3) stated_income_fill
        FROM promises_to_pay GROUP BY 1 ORDER BY 2 DESC"""),
    ("assignment", "Case assignment (randomised pilot)", """
        SELECT assignment_method, test_cell, count(*) n FROM collections_cases GROUP BY ALL ORDER BY ALL"""),
    ("cases_by_year", "Cases opened per year and 30-day cure rate", """
        SELECT substr(case_open_date, 1, 4) open_year, count(*) cases,
               round(avg((cure_flag = 'true' AND try_cast(days_to_cure AS INT) <= 30)::INT), 3) cure_30d
        FROM collections_cases GROUP BY 1 ORDER BY 1"""),
    ("case_status", "Case status", "SELECT case_status, count(*) n FROM collections_cases GROUP BY 1 ORDER BY 2 DESC"),
    ("model_scores", "Existing bank models", """
        SELECT model_name, model_version, entity_type, count(*) n, max(auc_at_validation) auc
        FROM model_scores GROUP BY ALL ORDER BY n DESC"""),
    ("benchmark", "Benchmark questions by split", """
        SELECT split, count(*) n, count(metric_id) with_metric FROM benchmark_questions GROUP BY 1"""),
]


def connect() -> duckdb.DuckDBPyConnection:
    s = get_settings()
    con = duckdb.connect()
    for p in sorted(s.bronze_dir.glob("*.parquet")):
        con.execute(f"CREATE VIEW {p.stem} AS SELECT * FROM '{p}'")
    return con


def to_markdown(cols: list[str], rows: list[tuple]) -> str:
    def cell(v: object) -> str:
        return "" if v is None else str(v).replace("|", "/").replace("\n", " ")[:120]

    out = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    out += ["| " + " | ".join(cell(v) for v in r) + " |" for r in rows]
    return "\n".join(out)


def main() -> None:
    s = get_settings()
    con = connect()
    results, md = {}, [
        "# Profiling report (generated)",
        "",
        "Generated by `scripts/profile/profile_all.py` from the bronze layer. Decisions based on these numbers are in "
        "[`profiling_decisions.md`](profiling_decisions.md).",
        "",
    ]
    for key, title, sql in CHECKS:
        t0 = time.perf_counter()
        rel = con.sql(sql)
        cols, rows = rel.columns, rel.fetchall()
        results[key] = {"columns": cols, "rows": [list(map(str, r)) for r in rows]}
        md += [f"## {title}", "", to_markdown(cols, rows), "", f"*{time.perf_counter() - t0:.1f} s*", ""]
        print(f"{key:24s} {len(rows):5d} rows")
    (s.reports_dir / "profile").mkdir(parents=True, exist_ok=True)
    (s.reports_dir / "profile" / "profile.json").write_text(json.dumps(results, indent=2))
    (ROOT / "docs" / "profiling_report.md").write_text("\n".join(md))


if __name__ == "__main__":
    main()
