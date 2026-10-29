# Maple Bank Collections Hackathon dataset (fully synthetic)

> **This is the small sample of the release**, drawn by `tools/make_sample.py` (seed 20260928): 5,560 CRM records and everything that belongs to them. Same layout and formats as the full release. The Rows column below is the sample's, not the release's. `files/voice` (WAV recordings) is not included. See `data/sample/README.md`.

Snapshot date: **2026-09-28**. History: October 2016 to September 2026. Customers: **5,560** CRM records (sample). One fictional bank ("Maple Bank"); every person, account, call and document is synthetic.

## Contents

| Table | Format | Rows | Path |
|---|---|---:|---|
| `customers` | CSV | 5,560 | `data/customers.csv` |
| `card_accounts` | CSV | 3,917 | `data/card_accounts.csv` |
| `loan_accounts` | CSV | 3,204 | `data/loan_accounts.csv` |
| `deposit_accounts` | CSV | 3,533 | `data/deposit_accounts.csv` |
| `collections_cases` | CSV | 5,873 | `data/collections_cases.csv` |
| `contact_history` | CSV | 66,391 | `data/contact_history.csv` |
| `promises_to_pay` | CSV | 6,556 | `data/promises_to_pay.csv` |
| `agent_notes` | CSV | 22,131 | `data/agent_notes.csv` |
| `call_transcripts` | CSV + JSON files | 1,597 | `data/call_transcripts.csv` |
| `voice_samples` | CSV + WAV files | 126 | `data/voice_samples.csv` |
| `external` | CSV | 2,215 | `data/external.csv` |
| `loan_instalments` | Parquet (by year) | 122,363 | `data/loan_instalments/` |
| `transactions` | Parquet (by year) | 173,824 | `data/transactions/` |
| `card_statements` | Parquet (by year) | 46,424 | `data/card_statements/` |
| `account_monthly_snapshot` | Parquet (by year) | 81,002 | `data/account_monthly_snapshot/` |
| `bureau_history` | Parquet (by year) | 11,324 | `data/bureau_history/` |
| `salary_credit_history` | Parquet (by year) | 27,636 | `data/salary_credit_history/` |
| `model_scores` | CSV | 43,034 | `data/model_scores.csv` |
| `offers` | CSV | 1,237 | `data/offers.csv` |
| `metric_definitions` | CSV | 15 | `data/metric_definitions.csv` |
| `benchmark_questions` | CSV | 35 | `data/benchmark_questions.csv` |
| `reference_documents` | CSV + Markdown files | 19 | `data/reference_documents.csv` |
| `hardship_programs` | CSV | 18 | `data/hardship_programs.csv` |
| `qa_checklist` | CSV | 10 | `data/qa_checklist.csv` |
| `agents` | CSV | 1,000 | `data/agents.csv` |
| `case_assignment_history` | CSV | 8,356 | `data/case_assignment_history.csv` |
| `agent_shifts` | CSV | 15,317 | `data/agent_shifts.csv` |
| `channel_capacity` | CSV | 287 | `data/channel_capacity.csv` |
| `ops_events` | CSV | 6 | `data/ops_events.csv` |
| `geo_reference` | CSV | 656 | `data/geo_reference.csv` |
| `code_lookups` | CSV | 113 | `data/code_lookups.csv` |

Other folders:

- `files/transcripts/YYYY/MM/<transcript_id>.json`: full call transcripts with the ordered `turns` (the `turn.*` fields of the data dictionary). `call_transcripts.csv` holds the call-level fields and the `file_path` to each JSON file.
- `files/voice/<voice_sample_id>.wav`: synthetic call recordings (text-to-speech, English), shipped separately as the optional
  voice pack because of its size; copy its `files/` folder here.
- `files/docs/...`: policy, procedure, script, incident and release-note documents for retrieval (`reference_documents.file_path`).
- `labels/benchmark_dev_answers.csv`, `labels/benchmark_answers_template.csv`: dev-split benchmark answers and the submission format (see Benchmark questions below).
- `labels/agent_notes_labels_public_500.csv`, `labels/call_transcripts_labels_public_500.csv`: 500 human-style gold labels each, for developing and testing NLP features. The rest are held out.
- `schema/`: `schema.json` (columns, types, descriptions), `ddl.sql` (ANSI CREATE TABLE), `load_duckdb.sql` (one-step load).
- `DATA_DICTIONARY.xlsx`: the data dictionary. `MANIFEST.csv`: every file with size and SHA-256.

## File conventions

- CSV: UTF-8, comma-separated, header row, RFC 4180 quoting. Empty field = null.
- Dates `YYYY-MM-DD`; timestamps `YYYY-MM-DD HH:MM:SS`. Timestamps are in the customer's local time unless the column name ends in `_utc`; operational events (`ops_events`) are Eastern Time.
- Some code values look like null markers to CSV readers: `NA` is the "no answer" outcome code and agent notes can
  literally contain `N/A` or `na`. In pandas use `pd.read_csv(path, keep_default_na=False, na_values=[""])` to keep them.
- Read identifier columns as text (for example `dtype=str` in pandas): some keys are all digits with leading zeros
  (the 10-digit CIF), and leading zeros matter for matching.
- Booleans `true` / `false`. Arrays and JSON values are JSON text (for example `["C-88213","L-5530921"]`).
- Parquet tables are Hive-partitioned by year (`year=2026/part-000.parquet`, zstd). Any Parquet reader works (DuckDB, pandas/pyarrow, Spark, polars, R arrow).
- Amounts are CAD unless `currency` says USD.

## Loading

```sql
-- DuckDB, from this folder
.read schema/load_duckdb.sql
SELECT current_bucket, count(*) FROM collections_cases WHERE outcome IS NULL GROUP BY 1;
```

```python
import pandas as pd
cases = pd.read_csv("data/collections_cases.csv")
statements = pd.read_parquet("data/card_statements")          # all years
```

```python
# Spark
spark.read.option("header", True).csv("data/customers.csv")
spark.read.parquet("data/loan_instalments")
```

## Customer keys

Each source system has its own customer key; there is no shared customer ID. Linking them into one customer (C360) is part of the challenge.

| System | Table / column | Key |
|---|---|---|
| CRM | `customers.crm_customer_id` | one per CRM record (a person can have two records) |
| Cards | `card_accounts.src_customer_ref` | card-system customer number |
| Lending | `loan_accounts.src_customer_ref` | borrower number |
| Core banking | `deposit_accounts.src_customer_ref`, `external.bank_subject_ref`, `bureau_history.bank_subject_ref` | 10-digit CIF |
| Collections | `collections_cases.coll_customer_ref` (copied from CRM at case open), `contact_history.crm_customer_id`, `promises_to_pay.crm_customer_id`, `agent_notes.crm_customer_id` | CRM ID |

Names, dates of birth, phones and postal codes are stored in each system's own format.

## Notes on the data dictionary

- Delinquency buckets: `current`, `1-30`, `31-60`, `61-90`, `91-120`, `121-150`, `151-180`, `180+`. Accounts are written off at 181 days past due on every product.
- `loan_accounts.product_type` includes `mortgage`. `collections_cases.primary_product` includes `mortgage` and `overdraft`.
- Two columns were added to `deposit_accounts`: `overdraft_dpd` and `overdraft_dpd_bucket` (delinquency of the overdraft facility).
- `contact_history` also holds system events (`channel = system`, `direction = internal`, `system_event_type` set).
- `collections_cases.current_treatment` uses the treatment of each stage: `sms_reminder`, `outbound_call`, `agent_call`, `senior_agent_escalation`, `legal_handoff`, `final_demand_letter`, `debt_sale`, `legal_recovery`, `hardship_review`.
- `account_monthly_snapshot` holds quarter-end snapshots (December 2023 to June 2026), plus charged-off accounts after write-off.
- `hardship_programs.policy_section` is a section of policy `POL-COLL-004` in `reference_documents`.
- Fields that need the real data to confirm were set from the generation rules.

## Benchmark questions (Layer 2)

`data/benchmark_questions.csv` holds the released benchmark. `split = dev` questions have their gold answers, reference SQL and
sources in `labels/benchmark_dev_answers.csv`, to develop against. `split = test` answers are hidden. More questions are
released at 19:00 IST on 4 October. Some questions should be refused; deciding which is part of the challenge.

Submit one CSV in the format of `labels/benchmark_answers_template.csv`, one row per question (released and extra):

| column | content |
|---|---|
| `question_id` | as in `benchmark_questions` |
| `answer` | your system's answer as text. For tables, a small CSV or one `key: value` per line is fine |
| `sql_or_sources` | the SQL your system ran, or the documents / sections / records it used |
| `refused` | `true` if your system declined to answer, else `false` |

Scoring is automatic: numbers are checked against the gold answer within each question's `tolerance`; document answers are
checked for the key facts and the cited document; refusals must be `refused = true` and other questions must not be refused.
Run your system as it is; do not edit answers by hand.

## Operational events

`ops_events` lists the incidents and releases the operations team knows about. Some data issues are not listed: finding them is part of the challenge.

## Privacy

All data is synthetic. Phone numbers are randomly generated and are not real: do not call or text them. Emails use the reserved `example.ca` / `example.com` / `example.net` domains. Voices are text-to-speech. Gender, marital status, citizenship, household, newcomer, accessibility, vulnerability and accent fields are included only to test fairness. They must not be used in decisions.
