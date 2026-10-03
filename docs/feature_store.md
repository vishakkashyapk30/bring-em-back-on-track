# Layer 3: Feature store

Reusable features from structured data and from text, with **one definition used for both training and live scoring**.

## One definition, two as-of points

Promise-level features are written once, in the dbt macro [`ptp_features(as_of)`](../pipeline/macros/ptp_features.sql):

| Store | Model | Evaluated as of | Rows |
|---|---|---|---|
| Offline (training) | [`features.f_ptp_offline`](../pipeline/models/features/f_ptp_offline.sql), exported to Parquet with a definition hash by [`features/build_offline.py`](../features/build_offline.py) | each promise's creation time, so nothing from after the promise leaks in | 238,815 promises (204,369 labelled) |
| Online (live scoring) | [`features.f_ptp_online`](../pipeline/models/features/f_ptp_online.sql) | the scoring time | 33,005 open promises |
| Online customer vector | [`features.f_customer_online`](../pipeline/models/features/f_customer_online.sql) | the snapshot | 86,044 customers with an open case |

The **parity check** ([`features/parity.py`](../features/parity.py)) recomputes 1,000 random online rows through the compiled shared definition and compares every column with what the online store serves: **0 mismatches across 38 columns**.

## Features

37 features are registered in [`features/registry.yaml`](../features/registry.yaml), each with entity, type, source, how it is built, when it becomes available, refresh and owner. The `/features` page reads the registry.

- **Structured (SQL):**
  - the promise itself: amount, days to due, prior broken promises, promise-to-overdue ratio, DPD at creation
  - the promise-vs-payday gap (A2)
  - case context
  - contact history in the 30 and 90 days before as-of
  - promise history in the case
  - customer cash stress (S7): NSF, days overdrawn, high-cost lender payments, EI deposits, payroll delay
  - bureau movement
- **Text (rule extractor):** hardship signal and reason, stated delay reason, dispute and complaint cues, cease requests and the agreed next step. They come from all 25,000 call transcripts and 760,594 agent notes ([`features/extract_text.py`](../features/extract_text.py), about 10 seconds), and are joined only when their `available_ts` (call end; note last edit) is before as-of.

## Text features are tested against human labels

Rules were mined from, and are measured against, the release's 500 public labels each ([`eval/eval_text_rules.py`](../eval/eval_text_rules.py)):

| Labels | Hardship (none/possible/clear) | Hardship reason | Hardship recall | Other |
|---|---|---|---|---|
| Call transcripts (500) | 99.6% | 99.6% | 100% | dispute 100%, complaint 100%, cease request 100%, next step 99%, **summary exact match 98%** |
| Agent notes (500) | 95.2% | 98.6% | 84.2% | |

The release notes that agent-coded hardship captures only about 60% of real hardship, so these text features add real signal. The public labels shaped the rules, so held-out accuracy may be a little lower.

## Not yet in the training features

Deposit and bureau values are only available as of the latest snapshot, not as history. They are used in the online customer vector and the NBA rules, but kept out of model training to avoid leakage.
