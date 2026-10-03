# Novel ideas register, scored on data feasibility

Purpose: pick what makes this design different, without promising anything the CSVs can't support. Every `table.column` below is machine-checked against the data dictionary by `design/novel_ideas_check.py` (run it after any edit; it must print OK).

Who it is for: **1. hardship and vulnerability manager (and specialists)**, **2. collections and strategy analyst**, and the agents on the NBA screen (**3**). Persona 2 was left blank in the request, so I filled it with what an analyst would need.

## How the scores work

**Data feasibility (DF), 1 to 5.** This is about whether the dictionary has the fields, at the right grain and coverage. It is not about whether the synthetic data contains the pattern; that is the separate "signal risk" column, which only profiling on 3 Oct can settle.

| DF | Meaning |
|---|---|
| 5 | Every field is listed, at full-population grain, no outside data and no unlisted label |
| 4 | Fields are listed, with one named limit (sample-only, thin coverage, an enum value we can't see) or one assumption we supply |
| 3 | Core fields are listed but a key input is missing or must be proxied, or the history must be built at run time |
| 2 | The main signal is probably not in the data; only a weak fallback |
| 1 | The needed data is not in the dictionary |

Novelty (1 to 5) and build effort (solo hours) are my judgement, not measured. Signal risk is Low / Med / High.

## Scoreboard

| ID | Idea | For | Layer | DF | Novelty | Effort | Signal risk | Verdict |
|---|---|---|---|---|---|---|---|---|
| H1 | Hardship plan simulator ("what-if") | Hardship manager | 4 | 4 | 4 | 8-10 h | Low | **Headline for persona 1** |
| S1 | Employer shock radar | Analyst | 3 + 2 | 4 | 5 | 6-8 h | **High** | **Headline for persona 2**, if profiling finds clusters |
| S2 | Collections weather map | Analyst | 2 | 5 | 3 | 3 h | Low | Core, it is S1's visual |
| H2 | Vulnerability review board + hardship latch | Hardship manager | Gov | 5 | 3 | 2 h | Low | Core (latch already in design) |
| H3 | Missed-offer finder + override audit | Hardship manager | 2 | 5 | 3 | 2 h | Low | Core, cheap |
| A2 | Promise vs payday check + what-if | Agent | 4 | 4 | 4 | 4 h | Med | Core |
| A1 | Paycheck-anchored windows | Agent / NBA | 3 + 4 | 4 | 3 | 4 h | Med | Core |
| S7 | Structured hardship early signals | Hardship / NBA | 3 | 4 | 3 | 3 h | Med | Core |
| S4 | Strategy scorecard, honest about causality | Analyst | 2 | 4 | 2 | 3 h | Med | Core (partly in design) |
| S3 | Data-health and schema-drift telemetry | Analyst / steward | 1 | 4 | 3 | 3 h | Med | Add-on, cheap |
| S6 | Capacity stress test ("plan B queue") | Analyst / team lead | 4 | 4 | 3 | 3 h | Low | Add-on |
| H5 | Outage-victim shield | Hardship / conduct | 1 + 4 | 3 | 4 | 4 h | Med | Add-on, strong fairness story |
| S5 | Query pre-flight (size and incident check) | Analyst | 2 | 3 | 3 | 2 h | Low | Add-on |
| A3 | Negotiation friction index | Agent | 3 | 3 | 4 | 3 h | **High** | Optional |
| H4 | Proxy-feature gate | Governance | 3 | 5 | 3 | 2 h | Low | Already in design (AUC 0.65 test) |

Not every idea fits one person in 36 hours. Section 7 gives a shortlist that does.

## 1. Persona 1: hardship and vulnerability manager

### H1. Hardship plan simulator (the "what-if" calculator)

**Idea.** A specialist moves levers (term extension, interest freeze, payment holiday, payment cut, fee waiver) and sees at once what the customer can afford and what the bank gives up. It is plain arithmetic on the account's real terms, so every number can be explained.

**Levers, and where each comes from**

| Lever | Allowed range comes from |
|---|---|
| Term extension | `hardship_programs.term_extension_max_months` |
| Payment cut | `hardship_programs.payment_reduction_pct` |
| Interest freeze or cut | `hardship_programs.rate_override` (nullable; a 0% value is **TBC**) |
| Payment holiday ("moratorium") | `collections_cases.hardship_plan_type` has `skip_payment`; `hardship_programs.duration_months` |
| Fee waiver | `hardship_programs.fees_waived_flag` |

A scenario inside one program's limits is allowed. One outside them is shown as "outside program rules, needs `hardship_programs.approver_level`" (exception policy **TBC**). Eligibility is the Use case 3 rule check (`hardship_programs.max_dpd`, `hardship_programs.min_months_on_book`, `hardship_programs.max_uses_12m`, `hardship_programs.excludes_broken_plan_90d`, `hardship_programs.excludes_insolvency`, `hardship_programs.requires_income_evidence`).

**What the simulator reads**

| Need | Fields |
|---|---|
| Loan terms | `loan_accounts.principal_balance`, `loan_accounts.accrued_interest`, `loan_accounts.fees_outstanding`, `loan_accounts.interest_rate`, `loan_accounts.rate_type`, `loan_accounts.scheduled_payment_amount`, `loan_accounts.payment_frequency`, `loan_accounts.remaining_term_months`, `loan_accounts.past_due_amount`, `loan_accounts.deferral_count_life` |
| Card terms | `card_accounts.current_balance`, `card_accounts.purchase_apr`, `card_accounts.minimum_payment_due` |
| Affordability | `deposit_accounts.payroll_avg_amount_3m`, `deposit_accounts.payroll_frequency_detected`, `deposit_accounts.essential_spend_amount_mtd`, `deposit_accounts.other_lender_payment_amount_mtd`, `deposit_accounts.cash_flow_volatility_6m`, `deposit_accounts.income_to_debt_service_ratio_est`, `customers.declared_annual_income`, `customers.income_verified_flag`, `external.total_monthly_obligations` |
| Bank impact | `collections_cases.total_exposure`, `collections_cases.expected_loss_est`, plus past charge-offs and recoveries (`loan_accounts.chargeoff_amount`, `loan_accounts.recovery_amount_to_date`, `card_accounts.chargeoff_amount`, `card_accounts.recovery_amount_to_date`) |
| Will the plan hold | `offers.program_id`, `offers.customer_response`, `offers.decline_reason`, `offers.plan_status`, `offers.plan_payments_due`, `offers.plan_payments_made`, `collections_cases.cure_flag`, `collections_cases.recidivism_flag` |

**What it shows**
1. New payment, and payment as a share of monthly surplus (income minus essential spend minus other lenders' payments).
2. Months to clear and total interest, against the current contract.
3. Bank impact: present value of the plan's cash flows against the status-quo path, where status-quo value is `total_exposure` less the bank's own `expected_loss_est`.
4. Chance the plan holds: the observed share of similar `offers` that stayed out of `broken`, by program, DPD band and affordability band. Labelled **"observed, not causal"**, because who was offered what was not random.
5. Approver level needed and the eligibility rule that passed or failed.

**Gaps (be honest in the pitch)**
- No discount rate, cost of funds or loss-given-default field exists. We state them as visible assumptions on screen (**TBC**).
- `essential_spend_amount_mtd` is month-to-date and already includes rent, so we do **not** subtract `customers.monthly_housing_cost` as well, and we scale it to a full month.
- The definition of `deposit_accounts.net_cash_flow_mtd` (before or after debt payments) is not stated, so it is a cross-check only (**TBC**).
- `card_accounts.min_payment_formula_code` (e.g. MP03) has no formula in `code_lookups`, so card scenarios are limited to a payment cut on `minimum_payment_due`. Whether `hardship_programs.product_types` covers cards is **TBC** (the example lists only personal and auto loans).
- Do not use `customers.household_size` or `customers.dependants_count` for affordability. They are protected attributes.

**Human review and audit.** The specialist decides; nothing reaches the customer from the simulator. Each scenario viewed and the one chosen go to `audit_log`.

**DF 4.** All levers and loan terms are listed. The assumptions above are the reason it is not a 5.

### H2. Vulnerability review board and hardship latch

- **Review board.** List customers whose `customers.vulnerability_review_date` is due or past, by `customers.vulnerability_source` and `customers.vulnerability_recorded_date`. Nothing falls off the radar silently.
- **Latch.** Models and rules can only raise `hardship_flag` to possible. Only a person lowers it, with a reason in `hardship_flag_events`. `collections_cases.hardship_source` already separates agent_coded, customer_form, model and llm_flag, so the board can show who or what raised each flag.
- Use `customers.vulnerability_flag` only. `customers.vulnerability_type` is a protected attribute.

**DF 5.** Already in design v2. The board is new.

### H3. Missed-offer finder and override audit

- **Missed offers.** Cases with `collections_cases.hardship_flag` set and `collections_cases.hardship_program_offered` false, newest first, with `collections_cases.hardship_reason`.
- **Override audit.** `offers.eligibility_result` has the value `ineligible_overridden`, so offers made against the rules are visible. Show them by agent and program, with `offers.nba_recommended_flag` to see whether the incumbent engine suggested them.
- **Why plans fail.** `offers.decline_reason` (still_unaffordable, wants_lower, will_pay_full, distrust, other) against `offers.plan_status`.

**DF 5.** All fields listed at case and offer grain.

### H4. Proxy-feature gate

Drop or bin any feature that predicts a protected attribute with AUC above 0.65, and report mutual information too. The 12 protected attributes plus `customers.age` are all present in `customers`, `deposit_accounts` and `voice_samples`, so the test can run. **DF 5.** Already in design v2.

### H5. Outage-victim shield

**Idea.** Do not chase, or charge, customers because of the bank's own outage. The dictionary's example row is an incident, INC-0914: a 14 Sep app outage where payments did not post until the next day and late fees were charged in error (`ops_events.description`, `ops_events.affected_customers_est`, est. 1,900). Whether that row is in the data is **TBC**; the idea works for any such event.

- Find accounts whose due date fell in `ops_events.start_ts` to `ops_events.end_ts` and that paid the next day: `card_statements.due_date`, `card_statements.first_payment_after_due_date`, `card_statements.days_late`, `card_statements.fees_amount`, `card_statements.fees_reversed_amount`, `loan_instalments.due_date`, `loan_instalments.paid_date`, `loan_instalments.days_late_when_paid`, `loan_instalments.fee_component`, `promises_to_pay.ptp_due_date`, `promises_to_pay.paid_date`.
- Compare our count with `affected_customers_est`, then propose fee reversal and a hold on pressure actions for a person to approve. Contacts already tagged with `contact_history.ops_incident_id` show who was chased.

**Gap.** The time a payment was attempted exists only in `transactions.txn_ts`, which covers a customer sample. Elsewhere we infer from due date and paid date, so the list is a candidate list. **DF 3.**

## 2. Persona 2: collections and strategy analyst

### S1. Employer shock radar

**Idea.** Layoffs and plant closures hit many customers at once, and a per-customer model sees each one only after they miss a payment. Group customers by employer and watch the group.

**Data check (this is the question that decides it).** Yes, the data supports an employer view:

| Need | Fields |
|---|---|
| Who works where | `customers.employer_name`, `customers.industry_naics2`, `customers.occupation_category`, `customers.employment_status`, `customers.employment_start_date`, `customers.pay_frequency` |
| Who actually pays them | `deposit_accounts.payroll_descriptor_raw` (e.g. "LAKESHORE AUTO PTS PAY" beside "Lakeshore Auto Parts Ltd."), `deposit_accounts.payroll_deposit_flag` |
| Payroll stopping | `deposit_accounts.payroll_delay_days`, `deposit_accounts.payroll_amount_change_pct`, `deposit_accounts.last_payroll_date`, `deposit_accounts.expected_next_payroll_date`, `salary_credit_history.gap_flag`, `salary_credit_history.employer_flag`, `salary_credit_history.credit_month`, `salary_credit_history.credit_amount_total` |
| Job loss confirmed | `deposit_accounts.ei_deposit_flag`, `deposit_accounts.ei_first_deposit_date` |
| Known shocks | `ops_events.event_type` has `external_economic`; `ops_events.description` |
| Link validation (sample only) | `transactions.payroll_employer_key`, `transactions.counterparty_name_clean`, `transactions.is_payroll_flag` |

**How it works**
1. Make an employer key from `customers.employer_name`, cross-checked against `deposit_accounts.payroll_descriptor_raw`. This is a second entity-matching job on the same Splink setup as customer matching. The stable `transactions.payroll_employer_key` gives a small answer key to measure the matching.
2. Per employer and week: customers with a payroll gap, customers whose `ei_first_deposit_date` is new, average `payroll_amount_change_pct`. Compare with the employer's own history and its `industry_naics2` peers.
3. Flag only employers with at least 10 linked customers (same suppression rule as Ask).
4. **Layoff-like** = payroll gap plus new EI deposits. **Payroll-processing delay** = payroll gap with no EI. Check `ops_events` before calling either.
5. Show on the weather map (S2) and hand the team lead a list of open cases and exposure (`collections_cases.total_exposure`) at that employer.

**Gaps**
- No column says "laid off". We detect payroll-gap clusters and infer cause, so we call it a radar, not a layoff detector.
- The values of `customers.employment_status` are not listed (**TBC**).
- `customers.employer_name` is declared at application and can be stale. The payroll descriptor is the better evidence of who pays today.
- `deposit_accounts` and `external` reach customers through identity matching (the dictionary says "via identity matching"); `salary_credit_history` already carries `crm_customer_id`.
- Whether the synthetic data has employer clusters at all is unknown. Hour-1 test: compare the share of customers with `payroll_delay_days` above 0 by employer against the overall share. If flat, fall back to industry or region and say so.
- **Scope.** The data contract allows collections servicing only. Contacting customers who are not yet delinquent needs Policy Office sign-off. The safe first uses are: reprioritise open cases, pre-check hardship eligibility, brief the team lead.

**Governance.** Employer is not a protected attribute, but it can stand in for one (e.g. newcomer status), so it goes through the proxy test (H4). Action is a team-lead batch approval, never automatic.

**DF 4. Signal risk High.** Highest novelty, and the only idea here that can look wrong if the data was not built with employer effects.

### S2. Collections weather map

Broken promises and roll rate by area, drawn as bubbles at each postal area's centre.

- Fields: `promises_to_pay.ptp_status`, `promises_to_pay.crm_customer_id`, `customers.fsa`, `customers.geo_lat`, `customers.geo_lon`, `geo_reference.centroid_lat`, `geo_reference.centroid_lon`, `geo_reference.cma_name`, `geo_reference.economic_region`, `geo_reference.broad_region`, `geo_reference.urban_rural`, `geo_reference.population_weight`, `account_monthly_snapshot.dpd_bucket`.
- `customers.geo_lat` is the postal-area centre, not the address, so the map is by area (FSA, metro area, region). A filled area map needs outside boundary files (public, not in the dataset); bubbles need nothing extra.
- It is a Canadian map (provinces and FSAs), not an Indian one.
- Areas with fewer than 10 customers are suppressed.
- Served through Ask, so every chart shows its SQL.

**DF 5** for bubbles; filled areas need outside boundary files.

### S3. Data-health and schema-drift telemetry

- Per load batch: row count, null rate, new or missing columns, value-set changes. Fields: `contact_history.batch_id`, `contact_history.extract_ts`, `contact_history.src_system`, `contact_history.record_hash`, `contact_history.src_file_name`, `customers.cdc_operation`, `external.file_received_ts`.
- The known case: `contact_history.channel_v2` replaced `contact_history.channel` on 26 Sep (the dictionary says "upstream release 26-Sep"). Detect it, then explain it using the release note: `reference_documents.doc_type` includes `release_note` and `reference_documents.related_table` names the table.
- Match dips to `ops_events.event_type` values `data_feed_issue` and `platform_release`, and to `ops_events.affected_tables`.
- Model drift on the same panel: `model_scores.psi_last_month`, `model_scores.auc_at_validation`, `model_scores.uses_protected_attributes`.

**DF 4.** A time series needs several batches in the files (`batch_id` suggests there are some, **TBC**).

### S4. Strategy scorecard that is honest about causality

Cure rate, cost per cure and complaints per 1,000 contacts by strategy, split by entry DPD and product so mix shifts don't mislead. Fields: `collections_cases.strategy_code`, `collections_cases.strategy_version`, `collections_cases.test_cell`, `collections_cases.assignment_method`, `collections_cases.entry_dpd`, `collections_cases.primary_product`, `collections_cases.cure_flag`, `collections_cases.days_to_cure`, `collections_cases.recidivism_flag`, `contact_history.contact_cost_cad`, `contact_history.complaint_raised_flag`. Only comparisons where assignment was random are marked causal (`collections_cases.assignment_method` values are **TBC**; `case_assignment_history.assignment_method` has `randomised_pilot`). **DF 4.**

### S5. Query pre-flight

Before an Ask answer, show how many rows or customers it covers against the whole portfolio, and any incident in the window (`ops_events.affected_tables`, `ops_events.start_ts`). Reuse `metric_definitions.default_filters` and `benchmark_questions.should_refuse`. The earlier draft also compared with "typical queries"; no query history exists in the CSVs, so that part builds up only after launch. The earlier "unintended updates" worry does not apply: Ask is read-only. **DF 3.**

### S6. Capacity stress test ("plan B queue")

If a dialer goes down or agents are absent tomorrow, which actions move to another channel or day, ranked by expected value? Fields: `channel_capacity.capacity_units`, `channel_capacity.used_units`, `channel_capacity.unit_cost_cad`, `channel_capacity.outage_flag`, `agent_shifts.absence_flag`, `agent_shifts.outbound_call_capacity`, `agent_shifts.evening_slot_capacity`, `agents.skill_hardship`, `agents.vulnerable_customer_certified`, `agents.current_case_load`, `agents.max_concurrent_cases`. **DF 4**: future-date rows are implied by `used_units` being null for future dates (**TBC**).

### S7. Structured hardship early signals

Transcripts exist for about 25,000 of 2.5M contacts, so the LLM `hardship_signal` is thin. Add a signal that exists for everyone: cash and debt stress. Fields: `deposit_accounts.nsf_count_mtd`, `deposit_accounts.overdraft_used`, `deposit_accounts.days_negative_mtd`, `deposit_accounts.high_cost_lender_txn_flag`, `deposit_accounts.other_lender_payment_count_mtd`, `deposit_accounts.income_to_debt_service_ratio_est`, `external.high_cost_lender_trades_count`, `external.bnpl_trades_count`, `external.off_us_delinquent_trades`, `external.inquiries_hard_3m`, `external.risk_score_delta_90d`, `external.revolving_util_trend_6m`. Bureau pulls are semi-annual (`bureau_history.pull_date`, `bureau_history.stale_score_flag`), so bureau parts go stale; they carry their pull date. It can only raise hardship to possible (the latch). **DF 4.**

## 3. Persona 3: agents on the NBA screen (ideas from the earlier draft, checked)

### A1. Paycheck-anchored windows (earlier idea 1)

Time reminders to when money arrives. Fields: `deposit_accounts.last_payroll_date`, `deposit_accounts.expected_next_payroll_date`, `deposit_accounts.payroll_frequency_detected`, `deposit_accounts.payroll_delay_days`, `customers.pay_frequency`, `promises_to_pay.customer_stated_income_date`, `contact_history.contact_hour_local`, `contact_history.answer_rate_prior_30d`, `channel_capacity.time_band`.

**Corrections to the earlier text**
- `hours_since_payroll_credit` and the "4 to 6 hour window after the deposit lands" cannot be built from `deposit_accounts`: it gives dates, not times. Times exist only in `transactions.txn_ts`, a 13-month customer sample. At full population this is **days** since and until payday.
- `channel_capacity.time_band` offers only 08-12, 12-17, 17-21 and all_day, so planned windows follow those bands.
- The bank already scores timing: `model_scores.entity_type` has `customer_hour_slot` and `customer_channel`, with `slot_rank`. We must beat that baseline.
- "Suppress calls when `payroll_delay_days` is above 0" is a policy hypothesis, not a data fact. Test it on `contact_history` outcomes before using it.

**DF 4 at day level; 2 at hour level.**

### A2. Promise vs payday check, plus promise what-if (earlier idea 3, narrowed)

While an agent takes a promise, show "this date is N days before your stated payday" and let them try another date, amount split or method; the break risk updates. Fields: `promises_to_pay.ptp_due_date`, `promises_to_pay.customer_stated_income_date`, `promises_to_pay.ptp_amount`, `promises_to_pay.ptp_to_overdue_ratio`, `promises_to_pay.days_to_due_at_creation`, `promises_to_pay.payment_method_promised`, `promises_to_pay.ptp_type`, `promises_to_pay.prior_broken_ptp_count`, `promises_to_pay.reminder_scheduled_flag`, `promises_to_pay.ptp_status`, `promises_to_pay.broken_reason_agent_coded`, `deposit_accounts.expected_next_payroll_date`, `model_scores.score`.

**Corrections.** The 0.81 to 0.34 example in the earlier draft is illustrative, not a result. A model re-scoring a changed date shows what it learned from history, **not** what would happen, so the screen says "model-implied". We test the idea first on history: break rate by (due date minus stated payday) bucket, and the share of `broken_reason_agent_coded` = no_funds in each. Whether `customer_stated_income_date` is filled often is **TBC**.

**DF 4.**

### A3. Negotiation friction index (earlier idea 2)

Fields: `call_transcripts.customer_talk_ratio`, `call_transcripts.silence_ratio`, `call_transcripts.overtalk_count`, `call_transcripts.hold_count`, `call_transcripts.turn.start_sec`, `call_transcripts.turn.end_sec`, `call_transcripts.turn.speaker`, `call_transcripts.turn.sentiment_score`, `voice_samples.dead_air_sec`.

**Corrections**
- `overtalk_count` is a total; it does not say who interrupted. "Agent overtalk" needs the per-turn times (`turn.start_sec`, `turn.end_sec`, `turn.speaker`) to attribute.
- "Dead air after an amount is proposed" needs the turn where the amount was said (an LLM can mark it); `voice_samples.dead_air_sec` is one total per call.
- Coverage is about 25,000 transcripts of ~2.5M contacts and 2,000 recordings. Only promises made on transcribed calls can be scored or checked.
- Silence and talk ratios can track disability or accent (`customers.accessibility_needs_flag`, `voice_samples.customer_accent_region` are protected), so it must pass the H4 proxy test, or it stays out.

**DF 3. Signal risk High.**

## 4. Other use cases from the brief, for completeness

| Use case | Data present | Missing | DF |
|---|---|---|---|
| Agent routing | `case_assignment_history.language_match_flag`, `case_assignment_history.continuity_flag`, `case_assignment_history.certified_for_vulnerable_flag`, `case_assignment_history.agent_cure_rate_90d_at_assignment`, `case_assignment_history.assignment_method` (`randomised_pilot`), `agents.skill_hardship` | Fairness care: agent attributes must not become customer proxies | 4 |
| Channel optimisation | `contact_history.link_clicked_flag`, `contact_history.link_payment_flag`, `contact_history.sms_reply_flag`, `contact_history.push_opened_flag`, `contact_history.contact_cost_cad` | `contact_history.email_opened_flag` is inflated by privacy proxies | 4 |
| QA automation | `qa_checklist.item_code`, `qa_checklist.pass_criteria`, `contact_history.qa_score`, `contact_history.qa_selected_flag` | `qa_checklist.item_no` says it "matches qaNN_ columns in call_transcripts", but no such columns are listed. Per-item truth labels are **TBC** | 2 |

## 5. Corrections to the earlier draft (summary)

1. Idea 1: hour-level payroll timing is not in `deposit_accounts` (A1).
2. Idea 2: overtalk is a total, not per speaker; coverage is about 1% of contacts (A3).
3. Idea 3: the 0.81 to 0.34 figure was illustrative, and the causal wording needs "model-implied" (A2).
4. Idea 4: no query history exists in the CSVs, and Ask is read-only (S5).
5. Idea 5: proxy gate (AUC 0.65) and the hardship latch are already in design v2 (H4, H2). The new part is the review board.

## 6. Open items to settle in hour 0 on 3 Oct

| Check | Decides |
|---|---|
| Distinct values and counts of `customers.employer_name`; share of customers in employers with 10+ people | S1 |
| Does the share with `deposit_accounts.payroll_delay_days` above 0 vary by employer? Any `ops_events.event_type` = `external_economic` rows and their dates | S1 |
| Values of `customers.employment_status` | S1 |
| Do any `hardship_programs` rows have `rate_override` of 0 or a card in `product_types`? | H1 |
| Share of promises with a non-null `promises_to_pay.customer_stated_income_date` | A2 |
| Number of distinct `batch_id` values per table | S3 |
| Values of `collections_cases.assignment_method` and `test_cell` hold-out size | S4 |
| Rows of `channel_capacity` with future dates | S6 |
| Does an employer-key match between `customers.employer_name` and `transactions.counterparty_name_clean` exceed 90%? | S1 |

## 7. Recommended shortlist for one person in 36 hours

The build plan has about 8 hours of "deepening" after the thin four-layer build, so only one headline idea can be built properly. The rest are designed in the PDF and, where cheap, built as a single feature.

| Pick | Ideas | Full effort | Build plan |
|---|---|---|---|
| Headline, persona 2 | S1 employer radar on the S2 map | 9-11 h | Build if hour-0 profiling finds employer clusters (section 6) |
| Headline, persona 1 | H1 plan simulator, with H3 missed offers and H2 review board | 12-14 h | Build if S1 has no signal; otherwise ship a loans-only H1 (about 6 h) and design the rest |
| NBA features | A2 promise vs payday, A1 day-level payday timing | 8 h | Built as 2 to 3 SQL features (about 2 h); what-if screens are design-only |
| Hardship signal | S7 | 3 h | One feature group (about 1.5 h) |
| Cheap extras | S3 drift panel, H5 outage list | 7 h | Design-only unless time is left |

All picks together are about 40 hours of work, so the PDF should present two headline ideas and mark what is built versus designed. If profiling finds no employer effect, S1 degrades to an industry-and-region view and H1 becomes the single headline.

## 8. Demo storyline (Ryan Mitchell, updated)

The employer step is only shown if profiling confirms an employer effect in the data.

1. **The trap.** Ryan is 38 DPD on a card; the legacy rules keep calling him in work hours.
2. **One view.** C360 links his records. His payroll is 29 days late (`deposit_accounts.payroll_delay_days`), and the employer radar shows his employer's other customers are late too, with new EI deposits (S1).
3. **The promise.** The agent sees the promised date falls before his stated payday and moves it (A2).
4. **The plan.** The hardship specialist opens the simulator, tries a 3-month cut, then a term extension, and sees affordability against bank cost (H1). The latch has already stopped pressure actions.
5. **The oversight.** The team lead sees the same employer cluster on the map and approves one batch for the other open cases there.
