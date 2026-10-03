# Data quality report (deliverable 4)

> **Status: template.** Issues already found during profiling, with counts, are listed in [`profiling_decisions.md`](profiling_decisions.md) §7. `governance/quality_report.py` regenerates this file from the pipeline run (`jobs nightly` or `make data`). Counts marked TBC are filled from the real data. The required content (per the build-phase instructions) is: **the issues found, how many records each affected, and how we handled them.**

- **Dataset:** Maple Bank synthetic release, snapshot 2026-09-28 (`data/raw/maple_collections_release/`)
- **Run:** TBC (timestamp, git commit, warehouse file)
- **Summary:** TBC issues found across TBC tables; TBC records affected; TBC blocking contract failures

## 1. Issues found

| # | Issue | Table(s) | Records affected | How we detected it | How we handled it | Contract rule |
|---|---|---|---:|---|---|---|
| 1 | Duplicate CRM records for one person (1,020,000 records for 1,000,000 people) | `customers` | TBC (~20,000 expected) | `duplicate_of_crm_id`, same `national_id_hash`, Splink | Linked to one `golden_id`; survivorship rules (most restrictive consent) | 5, 6 |
| 2 | Historical CRM versions | `customers` | TBC | `effective_to_ts` ≠ 9999-12-31 | Kept current rows only (not `is_deleted`) | 6 |
| 3 | Mixed date-of-birth formats | `customers`, source systems | TBC | Format parse per source | Parsed per source; ambiguous day/month flagged | n/a |
| 4 | Name format differences ("R. MITCHELL", "MITCHELL, RYAN JAMES") | card/loan/deposit name fields | TBC | Parse failures, Splink comparisons | Per-source name parser | n/a |
| 5 | Partly masked or inconsistent phones | `card_accounts`, `customers` | TBC | E.164 validation | Visible digits only used as partial evidence | n/a |
| 6 | Leading zeros on the 10-digit CIF | `deposit_accounts`, `external`, `bureau_history` | TBC | Length check after load | All identifiers read as text | n/a |
| 7 | `NA` outcome code and literal `N/A` in notes read as null | `contact_history`, `agent_notes` | TBC | Null-rate comparison | CSV read with only empty string as null | n/a |
| 8 | Schema drift: `channel` replaced by `channel_v2` (release 26 Sep) | `contact_history` | TBC | Schema hash per batch; release note REL-0926 | `coalesce(channel_v2, channel)` with a value mapping | n/a |
| 9 | Incident INC-0914: app payments posted next day, late fees charged in error | `card_statements`, `collections_cases`, `contact_history` | TBC (bank estimate 1,900 customers) | `ops_events`, incident report IR-2026-0914 | Affected promises excluded from model labels; caveat on Ask answers; H5 candidate list | n/a |
| 10 | Orphan keys (e.g. contacts whose case doesn't exist) | `contact_history`, `promises_to_pay` | TBC | Anti-joins | Kept, flagged; excluded from joins that need the parent | n/a |
| … | *Issues not listed in `ops_events` found by profiling* | | | | | |

## 2. Identity resolution

| Metric | Value |
|---|---|
| CRM records → golden IDs | TBC → TBC |
| Links by pass (deterministic / Splink / steward) | TBC / TBC / TBC |
| Precision / recall on labelled pairs | TBC / TBC |
| False-merge rate / false-split rate | TBC / TBC |
| Clusters sent to review (> 5 CRM records or weak internal pair) | TBC |

## 3. Contract tests (`gold.c360_customer`, DC-COLL-C360-001)

| Rule | Result |
|---|---|
| 1–11 | TBC (pass / warn / fail, with failing row counts) |

## 4. Freshness and drift

TBC: freshness per data product, schema hashes per batch, row-count and null-rate changes.
