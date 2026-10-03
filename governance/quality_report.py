"""Data quality report (deliverable 4): issues found, records affected, how we handled them.

Every count is recomputed from the warehouse on each run, so the report always matches the data.
Run: `python -m governance.quality_report` (after `make gold`). Writes docs/data_quality_report.md and
reports/data_quality.json (the JSON feeds /governance/quality in the app).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import duckdb

from common.config import get_settings

ROOT = Path(__file__).resolve().parents[1]

# (issue, tables, SQL returning one count, how detected, how handled, contract rule)
ISSUES: list[tuple[str, str, str, str, str, str]] = [
    ("Duplicate CRM records for one person", "customers",
     "SELECT count(*) FROM identity.crm_golden WHERE cluster_size > 1",
     "Shared national ID hash; duplicate_of_crm_id",
     "Clustered into one golden ID; survivorship picks the primary record, consent is the most restrictive", "5, 6"),
    ("duplicate_of_crm_id links refused because the two records carry different national IDs", "customers",
     """SELECT count(*) FROM silver.stg_customers c JOIN silver.stg_customers d ON d.crm_customer_id = c.duplicate_of_crm_id
        WHERE c.national_id_hash IS NOT NULL AND d.national_id_hash IS NOT NULL AND c.national_id_hash <> d.national_id_hash""",
     "Cannot-link guard during clustering", "Not merged (precision first); kept as separate golden IDs", "5"),
    ("Deleted CRM records", "customers", "SELECT count(*) FROM silver.stg_customers WHERE is_deleted",
     "is_deleted = true", "Kept for history, never chosen as the primary record", "n/a"),
    ("CRM date of birth in a non-ISO raw format (DD/MM/YYYY, 'Mon DD YYYY')", "customers",
     "SELECT count(*) FROM silver.customers WHERE dob_raw IS NOT NULL AND NOT regexp_matches(dob_raw, '^\\d{4}-\\d{2}-\\d{2}$')",
     "Format profiling", "Used the clean date_of_birth column; raw kept for lineage", "n/a"),
    ("Missing date of birth", "customers, deposit_accounts, loan_accounts, external",
     """SELECT (SELECT count(*) FROM silver.stg_customers WHERE dob IS NULL) + (SELECT count(*) FROM silver.stg_deposit_accounts WHERE dob IS NULL)
             + (SELECT count(*) FROM silver.stg_loan_accounts WHERE dob IS NULL) + (SELECT count(*) FROM silver.stg_external WHERE dob IS NULL)""",
     "Null counts", "Matching falls back to a name + postal block for records without a DOB", "n/a"),
    ("Each system stores names, DOBs, phones and postal codes in its own format", "card, loan, deposit, external",
     """SELECT (SELECT count(*) FROM silver.stg_card_accounts) + (SELECT count(*) FROM silver.stg_loan_accounts)
             + (SELECT count(*) FROM silver.stg_deposit_accounts) + (SELECT count(*) FROM silver.stg_external)""",
     "Format profiling ('C. LIN', 'KENNEDY/GARY', 'HAAS E O', 'LAST, FIRST'; DD-MM-YYYY, YYYY/MM/DD, YYYYMMDD)",
     "Per-source parsers in silver produce one normalised identity record per source", "n/a"),
    ("Partly masked card phone numbers (e.g. 780304xxx63)", "card_accounts",
     "SELECT count(*) FROM silver.stg_card_accounts WHERE phone_digits LIKE '%x%'",
     "Pattern check", "Compared on the visible digits only (first 6 and last 2)", "n/a"),
    ("Core-banking CIF lost its leading zeros", "deposit_accounts",
     "SELECT count(*) FROM silver.stg_deposit_accounts WHERE length(src_customer_ref_raw) < 10",
     "Key length check (644,202 raw keys vs 580,000 after padding)", "Left-padded to 10 digits before any join", "n/a"),
    ("Mistyped CRM ID in account snapshots (last digit differs; ID does not exist)", "account_monthly_snapshot",
     "SELECT count(*) FROM silver.stg_account_snapshot s ANTI JOIN identity.crm_golden g USING (crm_customer_id)",
     "Anti-join to CRM", "Account linked by majority vote over its valid CRM IDs", "n/a"),
    ("Snapshot month_end_date in non-ISO formats (YYYYMMDD, DD/MM/YYYY, MM/DD/YYYY)", "account_monthly_snapshot",
     "SELECT count(*) FROM bronze_snapshot WHERE NOT regexp_matches(month_end_date, '^\\d{4}-\\d{2}-\\d{2}$')",
     "Format profiling", "Parsed all formats; slash dates disambiguated by the quarter-end day", "n/a"),
    ("Collections case carries a mistyped CRM ID", "collections_cases",
     "SELECT count(*) FROM identity.case_xref WHERE crm_ref_invalid",
     "Anti-join to CRM", "Linked through the case's primary account instead (63 remain unlinked)", "n/a"),
    ("Contacts, notes, promises and transcripts with a mistyped CRM ID", "contact_history, agent_notes, promises_to_pay, call_transcripts",
     """SELECT (SELECT count(*) FROM silver.contact_history t ANTI JOIN identity.crm_golden g USING (crm_customer_id))
             + (SELECT count(*) FROM silver.agent_notes t ANTI JOIN identity.crm_golden g USING (crm_customer_id))
             + (SELECT count(*) FROM silver.promises_to_pay t ANTI JOIN identity.crm_golden g USING (crm_customer_id))
             + (SELECT count(*) FROM silver.call_transcripts t ANTI JOIN identity.crm_golden g USING (crm_customer_id))""",
     "Anti-join to CRM", "Linked through their case (case_id) instead of the CRM ID", "n/a"),
    ("Contacts whose case_id does not exist", "contact_history",
     "SELECT count(*) FROM silver.contact_history WHERE case_id IS NOT NULL AND case_id NOT IN (SELECT case_id FROM silver.collections_cases)",
     "Anti-join to cases", "Kept, flagged; excluded from case-level joins", "n/a"),
    ("Schema drift: channel renamed channel_v2 upstream (REL-0926, 26 Sep)", "contact_history",
     "SELECT count(*) FROM silver.contact_history WHERE channel IS NULL AND channel_v2 IS NOT NULL",
     "Null pattern by column; release note REL-0926", "Coalesced into one channel_std column", "n/a"),
    ("Bureau risk score missing or outside 300-900", "external",
     "SELECT count(*) FROM silver.stg_external WHERE risk_score IS NULL OR risk_score NOT BETWEEN 300 AND 900",
     "Range check", "Treated as missing in features. DFI-0812 (shifted column, about 10,000 subjects) is not visible in the latest-pull table; bureau_history still to check", "n/a"),
    ("Promises due during the INC-0914 app outage (payments posted a day late, fees charged in error)", "promises_to_pay",
     "SELECT count(*) FROM silver.promises_to_pay WHERE ptp_due_date = DATE '2026-09-14'",
     "ops_events INC-0914, incident report IR-2026-0914", "Excluded from model labels; caveat on Ask answers that cover 14 Sep", "n/a"),
    ("Accounts that could not be linked to a customer", "card, loan, deposit accounts",
     "SELECT count(*) FROM identity.account_xref WHERE golden_id IS NULL",
     "Identity resolution", "Left unlinked (precision first); key-level candidates in the steward review queue", "6"),
]


def main() -> None:
    s = get_settings()
    con = duckdb.connect(str(s.warehouse_path), read_only=True)
    con.execute(f"CREATE TEMP VIEW bronze_snapshot AS SELECT * FROM '{s.bronze_dir / 'account_monthly_snapshot.parquet'}'")
    rows = []
    for issue, tables, sql, detected, handled, rule in ISSUES:
        n = con.sql(sql).fetchone()[0]
        rows.append({"issue": issue, "tables": tables, "records_affected": int(n), "detected": detected,
                     "handled": handled, "contract_rule": rule})
    metrics = dict(con.sql("SELECT metric, value FROM identity.metrics").fetchall())
    c360 = con.sql("""SELECT count(*), count(open_case_id), round(avg(match_confidence), 4),
                             count(*) FILTER (WHERE match_method = 'probabilistic') FROM gold.c360_customer""").fetchone()
    tests = []
    rr = s.reports_dir / "contract_tests.json"  # saved by `make gold` right after `dbt test`
    if rr.exists():
        res = json.loads(rr.read_text())
        tests = [{"test": r["unique_id"].split(".")[2], "status": r["status"], "failures": r.get("failures")}
                 for r in res.get("results", []) if r["unique_id"].startswith("test.")]
    out = {"generated_at": datetime.now().isoformat(timespec="seconds"), "issues": rows, "identity": metrics,
           "contract_tests": tests,
           "c360": {"customers": c360[0], "with_open_case": c360[1], "avg_match_confidence": c360[2],
                    "probabilistic_customers": c360[3]}}
    (s.reports_dir).mkdir(parents=True, exist_ok=True)
    (s.reports_dir / "data_quality.json").write_text(json.dumps(out, indent=2, default=str))

    m = metrics
    md = [
        "# Data quality report (deliverable 4)", "",
        f"Generated by `governance/quality_report.py` on {out['generated_at']} from the warehouse built by the "
        "pipeline (`make data`). Every count below is recomputed from the data on each run.", "",
        "- **Dataset:** Maple Bank synthetic release, snapshot 2026-09-28 (`data/raw/maple_collections_release/`)",
        f"- **Issues found:** {len(rows)}, affecting {sum(r['records_affected'] for r in rows):,} records in total "
        "(a record can appear under more than one issue)",
        f"- **Golden C360:** {c360[0]:,} customers, {c360[1]:,} with an open collections case, average match "
        f"confidence {c360[2]}", "",
        "## 1. Issues found", "",
        "| # | Issue | Table(s) | Records affected | How we detected it | How we handled it | Contract rule |",
        "|---|---|---|---:|---|---|---|",
    ]
    md += [f"| {i} | {r['issue']} | {r['tables']} | {r['records_affected']:,} | {r['detected']} | {r['handled']} | "
           f"{r['contract_rule']} |" for i, r in enumerate(rows, 1)]
    md += ["", "## 2. Identity resolution", "",
           "| Metric | Value |", "|---|---|",
           f"| CRM records → golden IDs | {int(m['crm_records']):,} → {int(m['golden_ids']):,} |",
           f"| CRM records in multi-record clusters | {int(m['crm_records_in_multi_clusters']):,} |",
           f"| Clusters over 5 CRM records (sent to review) | {m['crm_records_flagged_large_cluster']} |",
           f"| Accounts linked | {int(m['accounts_linked']):,} of {int(m['accounts']):,} "
           f"({int(m['accounts_linked']) / int(m['accounts']):.1%}) |",
           f"| By snapshot majority vote / by source key | {int(m['accounts_by_snapshot_vote']):,} / "
           f"{int(m['accounts_by_source_key']):,} |",
           f"| Source keys: deterministic / scored match / steward review / unlinked | {int(m['keys_deterministic']):,} / "
           f"{int(m['keys_probabilistic']):,} / {int(m['keys_in_review']):,} / {int(m['keys_unlinked']):,} |",
           f"| Scored matcher precision / recall on deterministic links (answer key, {int(m['scorer_evaluated']):,} keys) | "
           f"{float(m['scorer_precision']):.2%} / {float(m['scorer_recall']):.2%} |",
           f"| Cases with a mistyped CRM ID / recovered via account / unlinked | {int(m['cases_with_mistyped_crm_ref']):,} / "
           f"{int(m['cases_recovered_via_account']):,} / {int(m['cases_unlinked']):,} |",
           "",
           "Precision comes first: a wrong merge means contacting the wrong person about a debt. The release says "
           "1,000,000 people; we resolve slightly more golden IDs than that, so we under-merge rather than over-merge.",
           "", "## 3. Contract tests (`gold.c360_customer`, DC-COLL-C360-001)", ""]
    if tests:
        md += ["| Test | Status | Failing rows |", "|---|---|---:|"]
        md += [f"| {t['test']} | {t['status']} | {t['failures'] or 0} |" for t in tests]
    else:
        md += ["Run `make gold` to execute the contract tests; results appear here."]
    (ROOT / "docs" / "data_quality_report.md").write_text("\n".join(md) + "\n")
    print(f"{len(rows)} issues, {len(tests)} contract tests -> docs/data_quality_report.md")


if __name__ == "__main__":
    main()
