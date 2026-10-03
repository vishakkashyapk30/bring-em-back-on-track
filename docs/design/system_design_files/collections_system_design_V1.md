# Bring em back on track

*Every customer in one place, Every answer in plain English, Every next step explained.*

| | |
|---|---|
| **Team** | Deep in Debt |
| **Member** | Vishak Kashyap K (solo) |
| **Event** | CIBC Collections Hackathon - System Design Round (V1: with the novel capabilities) |

## Part 1: Architecture diagram

![](diagrams/architecture_v1.png)

*Source: `diagrams/architecture_v1.py` (re-run it to regenerate the PNG, PDF and SVG). Layer 1 ends in the Gold C360 hub; Layers 2, 3 and 4 hang off it; governance is in section 10. The small tags (H1, S1, A2 and so on) are the capability IDs in section 7.*

## Part 2: Design doc

### 1. Summary

- **The problem.** Collections agents can't see the whole customer. Their story is spread across cards, loans, deposits, the CRM, cases, contact logs, notes, call transcripts and bureau files, each with its own customer ID. Wider trouble is just as hard to spot: a layoff at a big employer or a bank outage shows up as hundreds of missed payments nobody connects.
- **Three use cases on one platform.** The main one is Next Best Action (NBA). For every open case it suggests what to do, through which channel and when, explains why, and an agent approves or changes it. The second drafts notes after each call, which the agent checks before saving. The third is a call assistant that answers policy questions with sources, checks hardship eligibility, and lets a specialist try out repayment plans.
- **What is new.** I add 15 capabilities for three groups of people: hardship managers (H1, H2, H3, H5), analysts (S1 to S6), and agents and team leads (A1 to A3, S7). A sixteenth piece, H4, is a fairness check built into the pipeline. Section 7 rates each one on whether the data can really support it.

### 2. Business value

My main measure is the **30-day cure rate**. It is the share of cases opened in a week where the customer is back on track within 30 days, so it rewards recovery, not just cash collected. The share of promises kept moves sooner, so I watch it as the early signal.

- **How I count it.** A case is cured when `cure_flag` is true and `days_to_cure` is 30 or less. Cases on insolvency or deceased hold are left out. If `metric_definitions` has an approved cure formula, I use that (to be confirmed).
- **What must not get worse.** Three things stay at zero: pressure on customers in hardship, breaches of contact limits, and calls outside permitted hours. I also watch complaints per 1,000 contacts, customers who fall behind again within 90 days, the cost of each cure, and how often agents override the system. Anything above 25% gets a review.
- **How I test it.** On past data, I compare my promise-break model with the bank's current one (ptp_break v2.1 in `model_scores`, AUC 0.74) on the same later set of promises. In production it runs as a challenger to today's strategy, with a random hold-out.
- **For the new capabilities**, I track plan survival (H1), missed offers falling to zero (H3), how many days the employer alert leads the first missed payments (S1), broken promises by due-date-to-payday gap (A2), and wrong fees found after an outage (H5). For notes and the assistant: wrap-up time, edit rate and answer accuracy.
- **What it could be worth.** With about 2,800 new cases a month (to be confirmed), two more points of cure rate is about 56 more cures. If each saves a third of the expected loss (CAD 3,120 in the data's example), that is around **CAD 0.7M a year**.

### 3. Layer 1: Data Product Factory

This layer turns every source file into one trusted record per customer, the Gold C360.

**How data flows.** Files first land unchanged in a raw area (bronze). In the cleaning step (silver) I fix data types, keep only the current version of each CRM record (`effective_to_ts = 9999-12-31`, rather than `is_deleted`) and the latest monthly snapshot, and tidy up names, dates and phone numbers. The gold step builds the customer and account tables (`c360_customer`, whose contract is in Part 3, and `c360_account`), the links between people and accounts, and the identity tables. It also keeps four append-only tables: insights, model scores, NBA decisions and the audit log. Models train on monthly snapshots, statements and instalments, never on the wide `_m01` to `_m12` columns, because those were computed at a later date and would leak the future.

**Finding the same person in every system.** Cards and loans, deposits, the bureau and the CRM each have their own key, and one person can have several CRM records. I match in three passes inside a restricted zone, then swap personal details for tokens.

| Pass | What I compare | Outcome |
|---|---|---|
| 1. Exact keys | Same `national_id_hash` across CRM records (if the salt is shared, to be confirmed); `duplicate_of_crm_id`; `account_monthly_snapshot.crm_customer_id`; `bank_subject_ref` = deposit `src_customer_ref` | Linked automatically |
| 2. Fuzzy match (Splink) | Names vs `cardholder_name_raw`, `borrower_name_raw`, `holder_name_raw`; date of birth; phone; postal code; `pad_source_account` | A match probability |
| 3. Human review | An AI reads a masked pair; a data steward decides | Link or no link |

- **Messy data.** Birth dates come in four formats, and names appear as "R. MITCHELL" or "MITCHELL, RYAN JAMES", so I parse each source on its own terms. There is no true person ID to check against (to be confirmed). Instead, exact-key matches serve as known answers, I hand-label about 200 borderline pairs, and set the cut-off so 99.5% of automatic links are correct. Merging two people means calling the wrong person about a debt, so I would rather miss a link.
- **Safety rules.** A cluster can never contain two different national ID hashes, and any cluster with more than five CRM records goes to a person. Customers keep the same ID when I rerun. Name and birth date come from the current CRM record. For consent and do-not-contact flags I take the strictest value I find, and a hardship or vulnerability flag on any linked record applies to the customer.
- **Employer matching (S1).** The same tool links the employer a customer gave the bank (`customers.employer_name`) with the name on their pay deposit (`deposit_accounts.payroll_descriptor_raw`), for example "LAKESHORE AUTO PTS PAY" and "Lakeshore Auto Parts Ltd." A sample of transactions already carries a clean employer key (`transactions.payroll_employer_key`), so I can measure how well the matching works.
- **Data-health watch (S3).** Each load records row counts, missing values and table shapes, so I notice change. For example, `channel` in contact history was replaced by `channel_v2` on 26 Sep. I explain changes using release notes in `reference_documents` and incidents in `ops_events`; an AI drafts the fix and an engineer approves it.
- **Outage victims (H5).** When `ops_events` records an outage, I look for accounts that were due during it and paid the next day. They were probably charged late fees by mistake, and I compare my count with the bank's estimate. Payment times exist only for a sample, so this is a candidate list, not a final answer.

### 4. Layer 2: Insight and NLP

This layer lets people ask questions in plain English and get answers they can trust. Every question goes through one shared dictionary of business metrics, known as a semantic layer. I build it in MetricFlow from the bank's `metric_definitions` (formulas, filters and synonyms), and the feature store uses the same definitions.

1. **Understand the question.** Claude splits the question into metric, breakdown, filters and time period, shown as chips the analyst can correct.
2. **Refuse when needed.** If any part isn't allowed for that person's role, I refuse and say which part. Personal details and protected attributes are simply not in the dictionary, so nobody can ask for them.
3. **Write and check the SQL.** MetricFlow writes the query, and the AI only writes SQL itself when no metric fits. A checker (sqlglot) then makes sure the query only reads data, uses allowed columns, applies the user's row filter and has a row limit.
4. **Pre-flight (S5).** Each answer says how much of the portfolio it covers and flags incidents in the period, such as the 14 Sep app outage.
5. **Show the working.** Each answer comes with its rows, the SQL, how fresh the data is and any caveats. A written summary uses only those rows.

- **Analyst views.** They use the same path, so the SQL is always visible. The weather map (S2) shows broken promises and roll rates as bubbles at the centre of each postal area, and hides any area with fewer than 10 customers. The employer radar, scorecard and stress test are described in Layer 4, and the hardship views in use case 3.
- **Searching documents.** I search policies, agent notes and call transcripts (LanceDB), using only current versions for the right product and province. If I can't find a source, I don't answer. Text I retrieve is treated as information, never as instructions.
- **How I test it.** I run the organisers' benchmark with its tolerances and scoring, including questions that should be refused. Worked examples for the AI come from `metric_definitions`, minus any too close to a benchmark question. I also grade 30 search answers by hand.

### 5. Layer 3: Feature Store

This layer defines each model input once, so a model sees the same numbers in training and in live use. A registry records each feature's owner, source, refresh time and version, and how it is built (SQL, AI or voice analysis).

| Features | Built by | Source | Refresh |
|---|---|---|---|
| **Payday gap (A1, A2):** `ptp_due_minus_stated_payday`, days to `expected_next_payroll_date`, `payroll_delay_days` | SQL | `promises_to_pay`, `deposit_accounts` | Daily |
| **Employer cohort (S1):** share of customers with a payroll gap or new EI deposit, per employer, last 14 days | SQL | `deposit_accounts`, `salary_credit_history` | Daily |
| **Stress signals (S7):** `nsf_count_mtd`, `days_negative_mtd`, `high_cost_lender_txn_flag`, `external.bnpl_trades_count`, `risk_score_delta_90d` (keeps its pull date) | SQL | `deposit_accounts`, `external` | Daily, per pull |
| `hardship_signal`, `stated_delay_reason`, `ptp_intent_strength`, `dispute_signal` | AI | `call_transcripts.turns`, `agent_notes.note_text` | Per call |
| **Call friction (A3):** `customer_talk_ratio`, `silence_ratio`, `hold_count`, per-turn `sentiment_score`, `dead_air_sec` | Voice | `call_transcripts`, `voice_samples` | Per call |

- **The same numbers in training and in use.** Features are stored twice: an offline copy for training (Parquet) and an online copy with each customer's latest values (DuckDB, Redis in production). The same code builds both. Every value carries the time I could first have known it, so training on history never sees the future. Each night I recompute 1,000 online values the offline way and raise an alert if any differ.
- **AI features** are stored with the prompt version that produced them and their accuracy against hand labels. Only values an agent has approved reach the online store.
- **Fairness gate (H4).** If a group of features can predict a protected attribute (AUC above 0.65), I drop it or make it coarser. That includes the new employer, call and area features. From voice I use only call-level measures, never pitch, speaking speed or accent.
- **Coverage.** Only 25,000 of about 2.5 million contacts have transcripts, so text and voice features are marked present or missing, and poor recordings count as missing. That is why the stress signals (S7) matter: they exist for every customer.

### 6. Layer 4: Models and Decisioning

The three use cases share Layers 1 to 3. NBA gets the most depth; the other two reuse its transcripts, features and search.

| Use case | What runs | Who reviews |
|---|---|---|
| 1. NBA (main) | Policy gate, promise-break model, treatment ladder | Agent approves or overrides; team lead approves batches |
| 2. Post-call summary | AI fills a fixed form from the transcript | Agent edits and approves before saving |
| 3. Agent assist | Policy search, program rules, plan simulator | Agent decides; `approver_level` signs off above their level |

#### Use case 1: Next Best Action

An action has three parts: what to do (a reminder, a payment link, a plan offer, a referral to a specialist, or nothing), the channel (call, text, email, app notification or letter), and a time window (morning, afternoon, evening or any time, in the customer's time zone). In history, a promise is broken if it was missed or part-paid after the grace period, excluding promises due during a payment outage.

**Phase 1: what I build**

1. **Policy rules come first.** Before any model runs, plain rules remove what I must not do: no contact after a stop request, insolvency or death; a representative sends the case to a person; a dispute pauses it. I use only consented channels, permitted hours (never Sundays or holidays) and the weekly contact limit. A hardship or vulnerability flag removes pressure actions and routes the case to a trained agent.
2. **Promise-break model.** A LightGBM model predicts how likely each promise is to be broken. It is constrained so that more late payments never lower the risk, and tested on a later period. If it doesn't beat the bank's v2.1, I keep v2.1.
3. **Treatment ladder and payday timing (A1).** A low-risk promise gets no contact. A high-risk one due within three days gets a reminder in the window nearest the next payday, if that beats the bank's current timing scores on past data. A broken promise from someone whose pay is late gets a plan offer. Cases more than 30 days behind and at high risk get a call from an agent. Actions fill the day's channel capacity and agent shifts by expected value: break chance times amount at risk, minus contact cost. Payday timing is by day, as deposits have dates but no times.
4. **Promise check (A2).** While taking a promise, the agent sees how many days it falls before payday and can try another date or a split payment. The risk updates live, labelled **a model estimate, not cause and effect**. I first test it on history, comparing break rates by due-date-to-payday gap.
5. **Explanation.** Every suggestion explains itself in a fixed format, written without AI: which rules applied ("No call: 3 of 3 contacts used this week"), the main reasons behind the risk score ("Payroll 29 days late"), and what has changed.

**Phase 2: only if the checks pass**

An uplift model (EconML) estimates which action helps each customer most. It needs a real mix of past actions: if under 70% of open cases have comparable history, or any action has under 1,000 cases, I keep the rules and report that uplift can't be measured yet.

**Tools for team leads and analysts**

- **Team-lead playbooks (S1, H5).** These run daily and wait for a team lead's approval. Each week the employer radar counts customers with a late pay deposit, new Employment Insurance deposits and pay changes, and compares this with the employer's history and its industry. Only employers with 10 or more customers are shown. A pay gap with new EI looks like a layoff; without EI, more like a payroll delay. I check `ops_events` first, and since no field says "laid off", I call it a radar, not a layoff detector. The team lead sees the employer's open cases and exposure, and can reprioritise them or check hardship eligibility early. For outage victims (H5), it proposes refunding fees and pausing pressure. Contacting customers not yet behind needs Policy Office sign-off.
- **Stress test (S6) and scorecard (S4).** The stress test asks "what if a dialer fails or agents are off sick tomorrow?" and reruns the day's plan without them to show which actions move. The scorecard compares strategies on cure rate, cost per cure and complaints, by delinquency stage and product. A difference is called causal only when cases were assigned at random.

#### Use case 2: Post-call summary

After each call, the AI drafts notes from the redacted transcript: a summary of up to 80 words, any promise (amount, date, and how firm it sounded), signals such as hardship, the reason for the delay or a dispute, and next steps. Each item links to its part of the call, unsupported items stay blank, and a promise that differs from the recorded one is highlighted. The agent edits and approves the notes, and only approved values are saved.

#### Use case 3: Agent assist and hardship workbench

- **Policy answers and eligibility.** The agent can ask a policy question. The answer comes only from current documents for that product, province and language, and cites the document and section. Eligibility for each hardship program is decided by plain rules (days past due, months on book, uses in the last year, insolvency, recent broken plans), and the screen shows which rule passed or failed. The AI never decides eligibility.
- **Plan simulator (H1).** A specialist can try a longer term, a lower payment, an interest freeze or cut, a payment holiday or a fee waiver, within each program's limits in `hardship_programs`. Anything beyond them needs a higher approver. For each option it shows four things: the new payment against what the customer has left each month after essentials and other lenders (rent is already part of essentials); how long the debt takes to clear and the total interest; what the bank gives up compared with doing nothing; and how often similar plans have held in the past. Inputs missing from the data, such as discount rate and loss-given-default, are shown as stated assumptions. Cards only get a lower payment, as the card payment formula isn't defined (program coverage of cards to be confirmed). Household size and dependants are protected, so never used. Every scenario is logged.
- **Review board (H2) and missed offers (H3).** Managers see customers whose vulnerability review is due, hardship cases that were never offered a program, offers made even though the rules said no (by agent and program), and the reasons customers gave for turning plans down.

#### Where a person reviews

Plan offers, hardship and vulnerable cases, off-strategy actions, call summaries and program offers are always checked one at a time. Routine digital reminders and the team-lead playbooks are approved as a batch, with 2% checked first. Everything is logged, and anything can be overridden.

### 7. Novel capabilities, scored on data feasibility

I rated each idea on data feasibility (DF), meaning how well the data supports it. A 5 means every field I need is there in full, a 4 means there is one named limit or assumption, and a 3 means a key input is missing or has to be approximated. A script checks every field named here against the data dictionary; whether each pattern really exists I learn from profiling in the first hours.

| ID | Capability | Key fields | DF | Status |
|----|------------------------|------------------------------------|--------------|----------------------|
| H1 | Hardship plan simulator | `hardship_programs.payment_reduction_pct` | 4 | Headline, built |
| S1 | Employer shock radar | `customers.employer_name` | 4 | Built if data allows |
| S2 | Collections weather map | `geo_reference.centroid_lat` | 5 | Built |
| H2 | Review board + hardship latch | `customers.vulnerability_review_date` | 5 | Built with H1 |
| H3 | Missed offers + override audit | `offers.eligibility_result` | 5 | Built with H1 |
| A2 | Promise vs payday + what-if | `promises_to_pay.customer_stated_income_date` | 4 | Feature built |
| A1 | Payday-anchored windows | `deposit_accounts.expected_next_payroll_date` | 4 (day), 2 (hour) | Day-level built |
| S7 | Early hardship signals | `deposit_accounts.nsf_count_mtd` | 4 | Feature built |
| S4 | Honest strategy scorecard | `collections_cases.strategy_code` | 4 | Built |
| H4 | Proxy-feature gate | the 12 protected + `customers.age` | 5 | Built |
| S3 | Data-health telemetry | `contact_history.batch_id` | 4 | Designed |
| S6 | Capacity stress test | `channel_capacity.outage_flag` | 4 | Designed |
| H5 | Outage-victim shield | `ops_events.start_ts` | 3 | Designed |
| S5 | Query pre-flight | `ops_events.affected_tables` | 3 | Built as a banner |
| A3 | Negotiation friction index | `voice_samples.dead_air_sec` | 3 | Designed |

### 8. AI usage

| Where | What the AI does | Why not simple rules | How I check it |
|------------------------|-------------------------|------------------|----------------------------|
| Mapping, drift fixes (L1) | Suggests mappings, drafts fixes | 1,420 columns | Engineer approves; dbt tests |
| Identity, employer matching (L1) | Judges masked pairs | Nicknames, typos | Steward decides; answer key |
| Questions, search (L2) | Question to chips; cited answers | Free text, long documents | Allowlist, sqlglot, SQL shown, benchmark |
| Text features (L3) | Hardship signal, intent, delay reason | Only exists in text | Hand labels, prompt versions |
| Promise-break model, what-if (L4) | Ranks promises by break risk | Many signals interact | Beats v2.1, calibration, SHAP, "model-implied" label |
| Summary, policy answers (L4) | Drafts notes; answers from policies | Free speech, long documents | Form check, citations, agent approves |

**Where I deliberately avoid AI.** Policy rules, the ladder, eligibility, the simulator, the radar, explanations and refusals are plain rules or arithmetic, so every number can be audited. Only a person can clear a hardship flag.

### 9. Scalability

- **When things run.** Nightly, after files land (02:00 to 05:00 ET), I rebuild gold tables, identities and features, run parity and data-health checks, and prepare the NBA queue by 06:30 ET. Models are retrained and checked for fairness weekly. After a call, a payment, a broken promise or a new hardship flag, the case is re-scored within five minutes. Questions, customer lookups and the simulator respond in seconds.
- **Size.** About 1 million customers, 1.84 million accounts, 2.5 million contacts, 20 million instalments and 10 million transactions (the last for a sample of customers only). DuckDB and Splink handle this on a laptop. DuckDB has one writer, so approvals go to a side file merged nightly. AI over 1.5 million notes is the biggest cost, so open cases go first.

### 10. Governance

- **Access.** What people see depends on their role: agent, hardship specialist, team lead, analyst or data steward. Masking and row filters apply in the metric dictionary, SQL checker and document search. Employer and map views hide any group smaller than 10.
- **Protected attributes.** The dictionary marks 12: `gender_code`, `marital_status`, `citizenship_status`, `household_size`, `dependants_count`, `newcomer_program_flag`, `newcomer_arrival_date`, `accessibility_needs_flag`, `accessibility_type`, `vulnerability_type`, `ccb_deposit_flag` and `customer_accent_region`. I also leave out age, age band and voice characteristics. None of them feed a model or a rule. A restricted view uses them only to check outcomes and errors by group. The fairness gate (H4) also tests the new employer, call and area signals. I do use `vulnerability_flag`, because it can only make treatment gentler.
- **Hardship latch (H2).** A hardship signal is evidence from one call; the hardship flag is the customer's status (none, possible or clear). Any model, rule or agent can raise the flag to possible, and pressure stops straight away. A specialist confirms it by linking a program. Only a person can lower it, and they must record a reason. I measure hardship recall on 200 hand-labelled examples.
- **Monitoring and compliance.** I monitor drift, calibration, overrides, refusals, benchmark accuracy, hardship recall, contact-limit breaches and data health. Model documentation and versioned prompts follow OSFI E-23, contact rules FCAC and provincial limits, and privacy PIPEDA. An append-only audit log records every query, score, decision, edit, override and simulator run.

### 11. Build plan

**Tools.** I build with DuckDB, dbt, Splink, MetricFlow, sqlglot, Claude (on synthetic data), LanceDB, LightGBM, SHAP and Streamlit. Production swaps in Snowflake or Databricks, Dagster, Feast, Redis, MLflow, a bank-hosted LLM and live speech-to-text. Working alone, I build every layer and NBA thin, end to end, then go deeper. Hours run from 9:00 AM on 3 Oct, with five hours of sleep.

| Hours | Work |
|-----|--------------------------------------------------------------------------------------------|
| 0-3 | Profile the 31 tables and settle the open questions below; freeze the C360 schema |
| 3-12 | Layers 1 and 2, thin: pass-1 links, gold C360, contract tests; semantic layer, SQL check, refusals, pre-flight, benchmark run |
| 12-17 | Layers 3 and 4, thin: SQL features, parity check, promise-break model vs v2.1, gate, ladder, SHAP (then sleep, 17-22) |
| 22-24 | Streamlit: C360 view, Ask tab, agent workspace with approve/override, audit log |
| 24-32 | Go deeper: Splink pass 2; the **headline** chosen in hour 3 (S1 radar on the S2 map if employer clusters exist, else H1 simulator with H2, H3); text features; search; overlap check |
| 32-36 | Fairness audit including the proxy gate, monitoring view, final numbers, demo video, deck, README |

**Hours 0-3 pick the headline**: do late pay deposits cluster by employer (10+ customers), does `ops_events` hold economic events, and do programs allow 0% or cover cards? **Hour 24** is the checkpoint with a backup demo. **If time runs short**, I drop to exact-key matching, skip search and weak text features, and replace uplift with the overlap check.

## Part 3: Draft data contract (`gold.c360_customer` v1.0)

| Field | Value |
|---|---|
| Data product owner | Head of Collections Analytics (accountable for definitions and allowed uses) |
| Steward | Collections Data Engineering lead (pipeline, quality, identity review queue) |
| Policy approver | Collections Policy Office (consent, hardship and contact-block fields) |
| Grain | One row per golden_id (resolved person), current state |
| Consumers | Agent workspace, Ask (via the semantic layer), NBA feature table, employer radar, fairness audit view |
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
| `employer_key`, `payroll_delay_days` | string, int | Quasi-identifier (key tokenised) / None | Key from `customers.employer_name` matched to `deposit_accounts.payroll_descriptor_raw` (S1); max `deposit_accounts.payroll_delay_days` |
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
| 10 | `employer_key` match rate at least 90% on the `transactions.payroll_employer_key` sample (TBC) | Warn |

### Uses

```{=latex}
\noindent\begin{minipage}[t]{0.46\linewidth}
\textbf{Allowed}
\begin{itemize}
\item Collections servicing: the agent view and NBA
\item Collections analytics and reporting
\item Employer monitoring, in groups of 10 or more
\item Training and monitoring collections models
\item Fairness audits through the restricted view
\end{itemize}
\end{minipage}\hfill
\begin{minipage}[t]{0.5\linewidth}
\raggedright\textbf{Not allowed}
\begin{itemize}
\item Marketing or cross-selling
\item Credit decisions or limit changes
\item Any purpose outside collections
\item Contacting customers not yet behind, without Policy Office sign-off
\item Exporting direct PII outside the restricted zone
\item Joining protected attributes back in for decisions
\item Sending raw PII to an external LLM
\end{itemize}
\end{minipage}
```
