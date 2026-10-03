# Bring em back on track

*One view of each customer, answers in plain English, and a next step the agent can check.*

| | |
|---|---|
| **Team** | Deep in Debt |
| **Member** | Vishak Kashyap K (solo) |
| **Event** | CIBC Collections Hackathon, system design round |

## Part 1: Architecture diagram

![](diagrams/architecture.png)

*Source: `diagrams/architecture.py` (re-run it to regenerate the PNG, PDF and SVG). Layer 1 ends in the Gold C360 hub; Layers 2, 3 and 4 hang off it; governance runs along the bottom.*

## Part 2: Design doc

### 1. Summary

- **Problem:** an agent can't see a customer's full story. It is split across cards, loans, deposits, CRM, collections, contacts, notes, transcripts and bureau files, each with its own customer key.
- **Use cases:** three on one platform. **Next Best Action (NBA, primary):** for each open case we propose a treatment, channel and time window with the reasons, and a person approves or overrides it. **Post-call summary:** the LLM drafts structured notes from the transcript and the agent approves them. **Agent assist:** cited policy answers and a rule-based hardship program eligibility check during the call.
- **Users:** agents and hardship specialists act on it, team leads approve batches, strategy analysts ask questions, data stewards own the C360.

### 2. Business value

**Primary metric: 30-day cure rate**, by weekly cohort of new cases. It tracks customers getting back on track, not just cash collected. PTP kept rate is the leading indicator.

- **Definition:** cases with `cure_flag = true` and `days_to_cure <= 30`, divided by cases with `case_open_date` in the week, excluding `insolvency_hold_flag` and `deceased_hold_flag`. Formula from `metric_definitions` if it certifies a cure metric (TBC).
- **Guardrails (must not get worse):** pressure actions while `hardship_flag` is set = 0; `contact_cap_breach_count` and `out_of_hours_contact_count` = 0; complaints per 1,000 contacts (`complaint_raised_flag`); re-entry within 90 days of cure (`recidivism_flag`); `contact_cost_cad` per cure; agent override rate, reviewed above 25%.
- **Measured now, on history:** our PTP-break model against the bank's `model_scores` ptp_break v2.1 (AUC 0.74) on the same out-of-time promises. An off-policy cure estimate only where the Layer 4 overlap check passes. Randomly assigned `test_cell` cases, if any (TBC), come first because they need no causal assumptions.
- **In production:** a challenger cell against the champion with a randomised hold-out, using the existing `test_cell` set-up.
- **Other two use cases.** Post-call summary: `contact_history.wrap_duration_sec` and agent edit rate, on replayed calls then a rollout by team. Agent assist: accuracy on 40 held-out policy questions graded against `reference_documents`, and offers made outside `hardship_programs` rules (target 0).
- **Back of envelope:** ~340K cases over 10 years is ~2,800 new cases a month (TBC). +2 points of cure rate is ~56 extra cures a month. Each avoids a third of `expected_loss_est` (example CAD 3,120), so ~CAD 58K a month, **~CAD 0.7M a year** before contact savings.

### 3. Layer 1: Data Product Factory

**Pipeline.** *Bronze:* files land unchanged as Parquet. *Silver:* cast types, keep current CRM rows (`effective_to_ts = 9999-12-31`, not `is_deleted`) and the latest `snapshot_date` per account, standardise identity fields. *Gold:* `c360_customer` (contract in Part 3), `c360_account` (one row per account, all products in one shape), `account_party` (roles for `joint_holder_ref` and `co_borrower_ref`), `identity_xref` + `identity_events` (merge and split log), and append-only `interaction_insights`, `model_scores`, `nba_decisions`, `audit_log`. Training history uses `account_monthly_snapshot`, `card_statements` and `loan_instalments`, not the wide `_m01` to `_m12` columns, which are relative to 28 Sep 2026 and would leak.

**Customer matching.** Every source has its own key: `src_customer_ref` on cards and loans, the CIF on deposits and `external.bank_subject_ref`, a CRM ID in `coll_customer_ref`, and one person can have several CRM records. We run a Fellegi-Sunter style cascade on standardised values in a restricted zone, and tokenise PII after matching.

| Pass | Evidence | Result |
|---|---|---|
| 1. Deterministic | Equal `national_id_hash` across CRM records (if the salt is shared, TBC); `duplicate_of_crm_id`; `account_monthly_snapshot.crm_customer_id`; `bank_subject_ref` = deposit `src_customer_ref` | Auto link |
| 2. Splink | `first_name`/`last_name` vs `cardholder_name_raw`, `borrower_name_raw`, `holder_name_raw`; DOB; phone; postal code; `pad_source_account` | Probability |
| 3. Review band | LLM reads a masked pair; steward decides | Link or not |

- **Messy inputs.** DOBs come in four formats, names as "R. MITCHELL" or "MITCHELL, RYAN JAMES", card phones are partly masked. We parse per source and flag day/month ambiguity. A shared PAD account is evidence, not proof.
- **Thresholds.** No ground-truth person ID is listed (TBC). We hold out pass-1 links as labels, add ~200 hand-labelled pairs weighted towards borderline scores, and set cut-offs for 99.5% precision. A wrong merge means calling the wrong person about debt, so precision comes first.
- **Guards.** Two different `national_id_hash` values in one cluster is a hard cannot-link. Clusters over 5 CRM records, or with any internal pair below 0.5, go to review, not chain-merge.
- **Stable IDs.** On rerun a cluster keeps the golden_id of the old cluster it overlaps most. Merges keep the older ID and `identity_events` keeps aliases.
- **Survivorship.** Name and DOB from the current CRM row (DOB must agree with one other source or is flagged). Phone from `primary_phone_e164`; email only if verified and not bounced. Address from CRM unless `returned_mail_flag`, then the latest `address_since_date`. Consent, cease and do-not-call: most restrictive across linked records. `hardship_flag`, `vulnerability_flag`: set if any linked record is set.
- **AI helpers.** An LLM proposes source-to-C360 mappings and an engineer accepts each. Schema hashes catch drift (`channel_v2` replaced `channel` on 26 Sep) and the LLM drafts the fix as a pull request, never auto-merged.

### 4. Layer 2: Insight and NLP

The semantic layer is the only door to the data. We seed it from `metric_definitions` (formula, grain, `default_filters`, synonyms) as MetricFlow YAML, and the feature table reuses it.

1. **Parse.** Claude maps the question to tokens (metric, dimensions, filters, time, sort), shown as editable chips.
2. **Refuse by construction.** Any token off the role's allowlist is refused, saying which part. Direct PII and protected attributes aren't in the semantic layer, so they can't be asked for. An LLM intent check catches "list everyone's phone numbers".
3. **Compile.** MetricFlow compiles tokens to SQL. Only if no metric fits does the LLM write SQL, from few-shot examples.
4. **Validate.** sqlglot allows SELECT only, allowlisted columns, a role row filter and a LIMIT, on a read-only connection.
5. **Answer with working.** Rows, SQL, data products, freshness and caveats (`default_filters`, and any `ops_events` in range, e.g. the 14 Sep app outage that delayed payment posting). The LLM insight uses only returned rows.

- **Pre-built analytics.** "Which strategy worked best?" is cure rate by `strategy_code`; only comparisons inside randomly assigned `test_cell` groups are called causal, the rest say "observed, not causal" and split by entry DPD and product. "Top drivers of roll-rate deterioration" is a waterfall on `account_monthly_snapshot` (mix shift vs each segment's roll rate).
- **RAG** over `reference_documents`, `agent_notes` and `call_transcripts` (hybrid search, LanceDB). Current versions only (`superseded_by` null), for the right product and province. No citation, no answer. Retrieved text is data, never instructions. Agents see their own cases (`assigned_agent_id`), team leads their team, analysts aggregates with groups under 10 suppressed.
- **Evaluation.** We score the organisers' `benchmark_questions` (count TBC) with their `tolerance` and `grading_rubric` (numbers 60%, SQL 20%, caveats 20%), including `should_refuse` items. The few-shot library is written from `metric_definitions` before the benchmark is opened, and any example with embedding similarity above 0.9 to a benchmark question is dropped. LLM-judged RAG faithfulness is checked against 30 human-graded answers.

### 5. Layer 3: Feature Store

One set of feature definitions feeds both training and live scoring, and reuses the Layer 2 metric definitions, so "roll rate" or "DPD" means the same thing everywhere. A YAML registry lists name, entity, type, source, refresh, owner, version and built by (SQL, LLM or voice).

| Features | Built by | Source | Refresh |
|---|---|---|---|
| `dpd_max_current`, `worst_dpd_12m`, `ptp_broken_count_90d`, `ptp_to_overdue_ratio`, due date vs `expected_next_payroll_date` | SQL | `c360_account`, `promises_to_pay` | Daily |
| `payroll_delay_days`, `nsf_count_mtd`, `pad_returned_count_90d` | SQL | `deposit_accounts` | Daily |
| `risk_score_delta_90d` | SQL | `external` | Per bureau pull |
| `answer_rate_prior_30d`, link clicks (not `email_opened_flag`: Apple MPP inflates it) | SQL | `contact_history` | Daily |
| `hardship_signal` (none/possible/clear), `stated_delay_reason`, `ptp_intent_strength` (0 to 1, per promise), `dispute_signal` | LLM | `call_transcripts.turns`, `agent_notes.note_text` | Per call |
| `customer_talk_ratio`, `silence_ratio`, `overtalk_count`, `hold_count`, per-turn `sentiment_score`, `dead_air_sec`, `hold_music_sec` | Voice | `call_transcripts`, `voice_samples` | Per call |

- **Same values for training and scoring.** The offline store (Parquet, keyed by entity and `available_ts`) and the online store (latest row per entity; DuckDB, Redis in production) are written by the same dbt code. Training rows come from a point-in-time join "as of" each decision time (for promises, `ptp_created_ts`). A nightly parity check recomputes 1,000 random online rows through the offline path and alerts the steward on any mismatch.
- **Time known, not time of event.** Each value carries `available_ts`: `snapshot_date` plus extract lag for account data, the pull date for bureau data, `call_end_ts` plus extraction time for calls. A note counts only from `last_edited_ts`. This stops the model seeing the future.
- **LLM features** ship with their prompt version and accuracy against hand labels. A prompt change is a new feature version and a backfill. The post-call summary (use case 2) comes out of the same extraction call: the agent approves, and only approved values reach the online store.
- **Voice.** We use only call-level conversation metrics and two audio fields. Pitch, energy, speaking rate, filler rate and `customer_accent_region` stay out, because they can stand in for gender, age, accent or disability.
- **Coverage.** Only 25,000 of ~2.5M contacts have transcripts, so text and voice features carry `has_transcript` and notes widen coverage. Calls with `asr_confidence_avg` below 0.80 (TBC) mark text features low-confidence and the model treats them as missing. That `ptp_intent_strength` helps is a hypothesis, tested by training with and without text and voice features.

### 6. Layer 4: Models and Decisioning

Three use cases share Layers 1 to 3. NBA is primary and gets the most depth; the other two reuse the same transcripts, features, RAG index and review points, so they add little new build.

| Use case | Model or agent | Human review |
|---|---|---|
| 1. NBA (primary) | Policy gate, PTP-break LightGBM, treatment ladder | Agent approves or overrides each action; lead approves batches |
| 2. Post-call summary | Claude extraction to a fixed JSON schema | Agent edits and approves before anything is saved |
| 3. Agent assist | RAG over policies (Claude + LanceDB), rules over `hardship_programs` | Agent decides the offer; `approver_level` signs off above their level |

#### Use case 1: Next Best Action

**Action** = (treatment, channel, window). Treatment: reminder, payment_link, plan_offer (a `hardship_programs.program_id`), specialist_referral, no_contact. Channel: call, sms, email, push, letter. Window: `channel_capacity.time_band` in the customer's `time_zone`.

**Labels.** *PTP broken:* `ptp_status` in (broken, partially_kept) after `ptp_due_date + grace_days`; kept = 0; open and cancelled excluded; promises overlapping a payment-posting outage in `ops_events` dropped. *Cured:* `cure_flag` with `days_to_cure <= 30`, checked against `dpd_at_day_30 = 0`.

**Phase 1 (we build this).**

1. **Policy gate, plain rules, before any model.** `cease_communication_flag`, `cease_contact_flag`, `insolvency_hold_flag`, `deceased_hold_flag`: no contact. `third_party_rep_flag`: goes to a person. Open `dispute_status`: account pauses. Missing channel consent: channel not allowed. Calls only inside `permitted_call_start_local` to `permitted_call_end_local`, off Sundays unless `sunday_contact_permitted`, off holidays, under `contact_cap_7d`. `hardship_flag` or `vulnerability_flag` set: pressure treatments removed and the case routed to a `vulnerable_customer_certified` agent. (`national_dncl_flag` and CASL consent are marketing-only per the dictionary, so the gate ignores them.)
2. **PTP-break model.** LightGBM on Layer 3 features, with monotone constraints, isotonic calibration and a time-based split (train to Mar 2026, test Jul to Sep; TBC). If it doesn't beat v2.1 on the same promises, we keep v2.1 and say so.
3. **Treatment ladder, plain rules.** Low-risk open promise: no_contact. High risk and due within 3 days: reminder at the existing timing slot (`model_scores.slot_rank = 1`). Broken promise with `payroll_delay_days > 0`: plan_offer. 31+ DPD and high risk: agent call. Actions fill `channel_capacity` and `agent_shifts` by expected value: break probability × amount at risk − `contact_cost_cad`.

**Phase 2 (only if checks pass).** Uplift per action with an EconML DR-learner. We fit propensities per treatment and keep cases inside [0.05, 0.95]. If under 70% of open cases fall inside, or any action has under 1,000 cases there, we keep the ladder and report that uplift isn't identifiable (synthetic data may have no causal structure).

**Explanation, from reason codes in a fixed template, no LLM:** rules fired ("No call: 3 of 3 contacts used this week"), top SHAP drivers of the risk score ("Payroll 29 days late"), and what changed ("Promise PTP-0090311 broken"). SHAP explains risk only; in Phase 2 we also show the chosen action's estimated effect against the runner-up.

#### Use case 2: Post-call summary

When a call ends, the Layer 3 extraction call drafts a summary from `call_transcripts.turns` (already PCI and PII redacted). Fields: **summary** (up to 80 words: why the customer is behind, what was agreed), **promise** (amount, date, `ptp_intent_strength`), **signals** (`hardship_signal`, `stated_delay_reason`, `dispute_signal`, complaint and vulnerability cues), **next_steps**.

- **Explanation:** every field cites the turns it came from (`turn_index`) so the agent can click through; a field with no supporting turn is left empty.
- **Checks before the agent sees it:** the JSON must match the schema, and a promise amount or date must match the `promises_to_pay` row created on that `contact_id`. A mismatch is highlighted, not silently fixed.
- **Human review:** the agent edits and approves, aiming for under 30 seconds. Only approved values are saved and passed to the online store. Edits are logged, and the edit rate per field shows where the prompt needs work.

#### Use case 3: Agent assist

A side panel in the agent workspace, used during a call.

- **Policy answers.** The agent types a question ("Can a 45 DPD card customer get a payment deferral?"). RAG searches current `reference_documents` filtered by `applies_to_products`, `applies_to_provinces` and `language`, and Claude answers only from the retrieved sections, citing `doc_id` and section. No citation, no answer.
- **Eligibility, plain rules.** For a customer in hardship, the panel checks C360 values against each program's `max_dpd`, `min_months_on_book`, `max_uses_12m`, `excludes_insolvency` and `excludes_broken_plan_90d`, and shows the rule that passed or failed, plus `payment_reduction_pct`, `duration_months` and `requires_income_evidence`. The LLM never decides eligibility.
- **Prompts.** In the build we replay transcripts turn by turn to show prompts such as "hardship mentioned: check program eligibility". Live streaming ASR is a production step.
- **Human review:** nothing goes to the customer from the panel. The agent decides what to offer, and an offer above their level goes to the program's `approver_level` (hardship specialist or team lead).

#### Where a human reviews

**One by one:** NBA plan offers, settlements, hardship and vulnerable cases, anything off strategy, every post-call summary and every program offer; offers above the agent's level go to the `approver_level`. **By batch:** standard NBA digital reminders, approved by the team lead per strategy, 2% sampled before send, any item can be stopped. **Always:** everything is audited and overridable, and override and edit reasons feed monitoring.

### 7. AI usage

| Where | AI does | Why not rules | Checked by |
|---|---|---|---|
| Mapping, drift (L1) | Proposes mappings, drafts fix PRs | 1,420 columns | Engineer approves; dbt tests |
| Identity review (L1) | Verdict on masked pairs | Nicknames, typos, moves | Steward decides |
| Question parsing, RAG (L2) | Question to tokens; answers from policies, notes, transcripts | Free text, long documents | Allowlist, sqlglot, SQL shown, citations, benchmark |
| Text features (L3) | `hardship_signal`, intent, delay reason, dispute | Only exists in text | Stratified labels, prompt versions |
| PTP-break model (L4) | Ranks promises by break risk | Many interacting signals | Beats v2.1, calibration, SHAP, human approval |
| Post-call summary, agent assist (L4) | Drafts notes; answers policy questions | Free speech, long documents | Schema check, turn and doc citations, held-out questions, agent approves |

**Where we chose not to use AI:** the policy gate, the Phase 1 ladder, hardship program eligibility, survivorship, explanation text and the refusal guarantee are plain rules, because they must be predictable and auditable. Clearing a `hardship_flag` is always a person. **Hosting:** the build calls Claude on synthetic data; production uses a bank-hosted model with PII masked. Embeddings run locally.

### 8. Scalability

- **Nightly, done by 06:30 ET:** gold build after source extracts (02:00 to 05:00 ET), identity, offline and online features, parity check, next-day NBA queue, quality report. **Weekly:** retrain, calibration, fairness report.
- **Near real time, under 5 min:** text and voice extraction per call, online feature row update, then re-score on payment, broken promise, call end or `hardship_flag` raised. **Interactive, seconds:** NL questions and C360 lookup.
- **Scale:** ~1M customers, ~1.84M accounts, ~2.5M contacts, ~20M instalments, ~10M transactions (13 months, a customer sample only, so cash-flow features use deposit fields). DuckDB and Splink handle this on a laptop (DuckDB has one writer, so the app writes approvals to a separate file merged nightly). LLM extraction over 1.5M notes is the main cost, so open cases go first. Production adds Kafka events and the stack below.

### 9. Governance

- **Access.** By role (agent, hardship specialist, team lead, analyst, steward), with masking and row filters enforced in the semantic layer, the validator and RAG.
- **Protected attributes.** The dictionary marks 12: `gender_code`, `marital_status`, `citizenship_status`, `household_size`, `dependants_count`, `newcomer_program_flag`, `newcomer_arrival_date`, `accessibility_needs_flag`, `accessibility_type`, `vulnerability_type`, `ccb_deposit_flag`, `customer_accent_region`. We also exclude `age`, `age_band` (a protected ground in Canada) and voice acoustics. None are features, gate inputs or semantic-layer objects; a restricted view uses them only to audit action rates, cure rates and model errors by group. **Proxy test:** a feature group (e.g. `fsa_income_index`, `cpp_oas_deposit_flag`) that predicts a protected attribute with AUC above 0.65 is dropped. `vulnerability_flag` is allowed because it can only make treatment gentler.
- **Hardship.** `hardship_signal` is raw per-call evidence; `hardship_flag` is the customer's current state (none, possible, clear, as in `hardship_programs.min_hardship_level`). *Raise:* any signal or agent sets possible and pressure actions stop at once; a false alarm only costs a gentler contact. *Confirm:* a specialist confirms and links a program. *Lower:* only a person, with a reason in `hardship_flag_events`. *Measure:* recall on 200 hand-labelled transcripts and notes with at least 70 positives, sampled using `hardship_mentioned_flag` and keywords, not the LLM under test.
- **Human review** is tiered as in Layer 4. **Monitoring and compliance:** PSI, weekly calibration, overrides, refusals, benchmark accuracy, hardship recall, cap breaches. Model cards and versioned prompts follow OSFI E-23; contact rules follow FCAC and provincial limits (e.g. Ontario's hours and frequency); privacy follows PIPEDA. The audit log is append-only, write-once in production.

### 10. Build plan

| Part | Build with | Production equivalent |
|---|---|---|
| Layer 1 | DuckDB, dbt, Splink, dbt tests | Snowflake or Databricks, Dagster, Splink on Spark |
| Layer 2 | MetricFlow, sqlglot, Claude, LanceDB | Same, bank-hosted LLM |
| Layer 3 | dbt feature models, Parquet offline + DuckDB online, YAML registry | Feast with Redis |
| Layer 4, app | LightGBM, SHAP, Claude, LanceDB, Streamlit | MLflow, internal web app, streaming ASR |

I'm building this alone, so the plan is sequential: a thin version of all four layers and the primary use case end to end first, then deepen. Hours count from 9:00 AM, 3 Oct and include a 5-hour sleep.

| Hours | Work |
|---|---|
| 0-3 | Profile the 31 tables, close TBCs, freeze the C360 schema |
| 3-8 | Layer 1 thin: silver, pass-1 deterministic links, gold C360, contract tests |
| 8-12 | Layer 2 thin: semantic layer from `metric_definitions`, tokens to SQL, sqlglot guard, refusals, first benchmark run |
| 12-17 | Layers 3 and 4 thin: SQL features with point-in-time join and parity check, labels, PTP-break model vs v2.1, policy gate, ladder, SHAP reason codes |
| 17-22 | Sleep |
| 22-24 | Streamlit: C360 view, Ask tab, agent workspace with approve/override, audit log |
| 24-32 | Deepen, in order: (1) Splink pass 2, survivorship, stable IDs, quality report; (2) hardship flow and labelling; (3) text and voice features and the post-call summary screen; (4) RAG with citations and the agent assist panel; (5) Phase 2 overlap check |
| 32-36 | Fairness audit, monitoring view, final eval numbers, demo video, deck, README |

**Hour 24 (9:00 AM, 4 Oct) is the demo-safe checkpoint:** I tag the build and record a backup demo of the C360 view, benchmark answers with SQL and refusals, and NBA with explanation and override. **Cut lines:** if matching runs late, the C360 ships on pass-1 links and the review band is shown as a design. A text feature below its accuracy bar stays out. If RAG doesn't make it, Ask answers SQL questions only and agent assist ships the eligibility check alone. Phase 2 uplift is beyond 36 hours for one person; I run the overlap check and report it. Hand labels (~2.5 h, all mine): ~200 identity pairs, 200 hardship snippets, 30 RAG answers. **Future work:** Phase 2 uplift, live streaming for agent assist, call QA against `qa_checklist` as a fourth use case.

## Part 3: Draft data contract (`gold.c360_customer` v1.0)

| Field | Value |
|---|---|
| Data product owner | Head of Collections Analytics (accountable for definitions and allowed uses) |
| Steward | Collections Data Engineering lead (pipeline, quality, identity review queue) |
| Policy approver | Collections Policy Office (consent, hardship and contact-block fields) |
| Grain | One row per golden_id (resolved person), current state |
| Consumers | Agent workspace, Ask (via the semantic layer), NBA feature table, fairness audit view |
| Refresh | Daily batch after source extracts, landed by 06:30 ET; `hardship_flag` and consent changes event-driven in production |
| Freshness SLA | `_refreshed_at` no older than 26 hours; alert to steward on breach |
| Retention | Follows source retention (7 years on notes and recordings); exact period TBC |

### Schema

| Column | Type | PII class | Source and rule |
|----------------------|--------------|----------------|------------------------------------------------|
| `golden_id` | string | None | Generated; stable across reruns |
| `crm_customer_ids` | array\<string\> | Internal key | `customers.crm_customer_id` via `identity_xref` |
| `match_method`, `match_confidence` | enum, decimal(4,3) | None | deterministic / probabilistic / reviewed; lowest link probability in the cluster |
| `display_name` | string | Direct PII, masked for analysts | `preferred_name`, else `first_name` + `last_name` |
| `phone_token`, `email_token` | string | Direct PII, tokenised | `primary_phone_e164`; `email` (verified, not bounced) |
| `province_code`, `fsa`, `time_zone`, `preferred_language` | enum, string | Quasi-identifier | `customers.*`; `time_zone` checked against `geo_reference.time_zone` |
| `consent_call`, `consent_sms`, `consent_email`, `consent_push` | boolean | None | `customers.consent_*`, most restrictive across linked records |
| `permitted_call_start_local`, `permitted_call_end_local` | string HH:MM | None | `customers.permitted_call_*_local` |
| `contact_block` | enum | None | none / cease / insolvency / deceased / represented, from `cease_communication_flag`, `bankruptcy_flag`, `consumer_proposal_flag`, `deceased_flag`, `credit_counselling_agency_flag`, `legal_representative_flag` |
| `hardship_flag` | enum | Sensitive, not protected | none / possible / clear, from `collections_cases.hardship_flag`, `hardship_mentioned_flag`, `hardship_signal` |
| `vulnerability_flag`, `dispute_open_flag` | boolean | Sensitive, not protected / None | `customers.vulnerability_flag`, `collections_cases.vulnerable_customer_flag`; `dispute_status = open` or `card_accounts.dispute_open_flag` |
| `max_dpd`, `total_past_due_cad` | int, decimal(12,2) | None | Max `dpd` and sum of `past_due_amount` over open accounts in `c360_account` |
| `open_case_id`, `_refreshed_at` | string, timestamp | None | `collections_cases.case_id` where `case_status = open` (values TBC); pipeline run time |

### Quality rules

Each rule is a dbt test; a failure blocks publish unless marked warn.

| # | Rule | Severity |
|--|----------------------------------------------------------------------------|-------|
| 1 | `golden_id` is unique and not null | Error |
| 2 | `match_confidence` between 0 and 1, and at or above the auto-merge cut-off unless `match_method` is deterministic or reviewed | Error |
| 3 | Cross-field: `max_dpd > 0` implies `total_past_due_cad > 0` (`max_dpd = 0` with more than CAD 1 past due: warn) | Error |
| 4 | Consent flags are never null and never more permissive than any linked current CRM record | Error |
| 5 | No golden_id links two different non-null `national_id_hash` values | Error |
| 6 | Every current CRM record maps to one golden_id; every `c360_account` row has one primary party | Error |
| 7 | Every change of `hardship_flag` down to none has a `hardship_flag_events` row with a reviewer and reason | Error |
| 8 | No protected-attribute column (the 12 in Governance, plus `age`, `age_band`) exists in this table | Error |
| 9 | `_refreshed_at` is within the last 26 hours | Error |

### Uses

**Allowed:** collections servicing (agent view, NBA); collections analytics and reporting; training and monitoring of collections models; fairness audit through the restricted view. **Prohibited:** marketing or cross-sell; credit adjudication or limit changes; any non-collections purpose; export of direct PII outside the restricted zone; joining back protected attributes for decisions; sending raw PII to an external LLM.
