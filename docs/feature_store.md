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

55 features are registered in [`features/registry.yaml`](../features/registry.yaml), each with entity, type, source, how it is built, when it becomes available, refresh and owner. The `/features` page reads the registry.

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
| Call transcripts (500) | 99.6% | 99.6% | 100% | dispute 100%, complaint 100%, cease request 100%, next step 99%, stated delay reason 90.4%, **promise firmness 100%**, **summary exact match 98%** |
| Agent notes (500) | 95.2% | 98.6% | 84.2% | |

Promise firmness (`ptp_intent_strength`) has two gold levels, 0.85 for a plain commitment ("I can pay $200 the 24th") and 0.45 for a hedged one ("I'll try to pay $64 next payday"). The rule (hedge words such as "try to", "maybe", "hopefully", and the French equivalents, in the customer's own promise turns) matches the label on 500 of 500 transcripts (100%). The rule was mined from the same 500 labels, so held-out accuracy may be lower.

**Poor recordings count as missing.** A call with `asr_confidence_avg` below 0.80 (the v2 rule, now our decision) gets its text features set to missing, not guessed: `features.text_rules.extract(..., asr_confidence_avg=...)` returns empty values and `low_confidence = True`, and the post-call draft says the recording quality was poor.

**Registry.** The text features are registered with `built_by: ai`, provider `offline` (the rule extractor), prompt `text_features`, prompt version 1 and the accuracy above. The allowed values of `built_by` are `sql`, `ai` and `voice`. Per-call features: `hardship_signal`, `stated_delay_reason`, `dispute_signal`, `complaint_cue`, `ptp_intent_strength`. No voice acoustic or protected-attribute feature is registered.

The release notes that agent-coded hardship captures only about 60% of real hardship, so these text features add real signal. The public labels shaped the rules, so held-out accuracy may be a little lower.

## Not yet in the training features

Deposit and bureau values are only available as of the latest snapshot, not as history. They are used in the online customer vector and the NBA rules, but kept out of model training to avoid leakage.

## Credit and account history features (added 4 Oct)

Eighteen promise-level features read the bank's own history as of the moment the promise was made, in the same macro (so training and live scoring still share one definition; the parity check recomputes 1,000 live rows with 0 mismatches over 56 columns): `bur_*` (latest bureau pull on or before the date: score, revolving utilisation, delinquent trades, hard inquiries, stale flag), `sal_*` (salary credits in the three whole months before the promise month), `card_*` (the last card statement whose due date has passed: utilisation, minimum or full payment, days late, delinquent cycles, payment over minimum) and `snap_*` (the latest month-end account snapshot within 120 days). They lifted the promise-break model from AUC 0.667 to 0.712 on its own (see [`model_card_ptp_break.md`](model_card_ptp_break.md)). One of them leaked before it was fixed: a card statement's `days_late` comes from the first payment after the due date, which can fall after the promise, so it is used only when that payment had already happened.
