# Profiling decisions (hour 0 to 3)

Decisions taken after profiling the released data on 3 Oct. The numbers come from [`profiling_report.md`](profiling_report.md) (regenerate with `make profile` after `make bronze`). Each decision says what we chose, the evidence, and what it changes.

## 1. Headline novel capability: H1 hardship plan simulator

**Decision:** build **H1, the hardship plan simulator**, with **H2 (vulnerability review board)** and **H3 (missed offers and override audit)** as its companions. **S1 (employer shock radar) is not built**; it stays in the design as an idea the data didn't support.

**Evidence:**
- `ops_events` has a real shock, **ECO-0715**: auto-parts plant layoffs in Windsor-Essex, 15 Jul to 28 Sep 2026, about 4,000 customers.
- The data doesn't show it at employer or regional level. Manufacturing payroll in Windsor-Essex has 7.3% of deposits more than 7 days late, against 7.8% for manufacturing elsewhere; EI share 8.6% vs 8.4%. Cases opened in Windsor-Essex follow the national monthly pattern, with the same hardship share.
- Employer names are city-tagged (e.g. "(Toronto)", "(Montréal)") and never name Windsor, and payroll descriptor groups are small (3,533 descriptors with 10+ accounts, most under 25).
- H1 is fully supported: current programs cover **cards** (HP-CARD-MIN, HP-CARD-RATE, HP-CARD-SKIP, HP-CARD-FPP), **loans** (HP-LOAN-RED3, HP-LOAN-EXT with up to 12 months' term extension, HP-LOAN-SKIP), lines of credit, overdraft (HP-OD-REPAY), a debt management plan (HP-DMP) and settlement (HP-SETTLE). **0% rate overrides exist** (HP-CARD-FPP, HP-DMP).

**Changes:** ECO-0715 becomes an incident caveat (Ask pre-flight and the hardship board), not a radar. The demo storyline leads with the simulator.

## 2. Customer identity: deterministic bridges first

**Decision:** match in this order, then send what's left to Splink and the steward.

| Bridge | Evidence | Use |
|---|---|---|
| CRM to CRM: same `national_id_hash` | 954,762 records carry a hash; 18,496 hashes repeat across records | Link (cannot-link if two different non-null hashes meet) |
| CRM to CRM: `duplicate_of_crm_id` | 5,950 records; 5,518 of them also share a national ID hash | Link |
| Account to CRM: `account_monthly_snapshot.crm_customer_id` | 1,635,858 accounts appear in snapshots; about 2.6% of snapshot rows carry a **mistyped CRM ID** (differs in the last digit, doesn't exist in CRM) | **Majority vote over valid IDs** per account links **1,632,286 accounts (99.8%)**. 42,092 accounts point to two valid CRM IDs: evidence the two records may be one person, sent to the review band |
| Source key propagation | One `src_customer_ref` covers several accounts (550,000 card keys for 660,000 accounts; 340,000 lending keys for 404,500) | Once one account of a key is linked, its other accounts follow |
| Core banking CIF | **156,837 CIFs lost their leading zeros**: 644,202 raw keys collapse to 580,000 after `lpad(…, 10, '0')`. The bureau (`external.bank_subject_ref`) uses the same CIF | Normalise to 10 digits before any join |
| Remainder | About 208,000 accounts never appear in a quarter-end snapshot (opened after June 2026, or short-lived) | Splink on name, DOB, phone and postal code (each system's own format), then steward review |

The five source systems (and their keys) are confirmed by the release README: CRM, Cards, Lending, Core banking (CIF) and Collections (CRM ID copied at case open).

## 3. Settled open questions

| Question | Decision | Evidence |
|---|---|---|
| Sunday contact | Never call on Sundays (V1 wording). `sunday_contact_permitted` is read but does not unlock Sunday calls. Decided 3 Oct: no Sunday calls for anyone (spec wording, and agents get a day of rest) | The specification suite tests V1 as primary; the switch keeps the v2 reading one line away |
| "clear" means two things | Keep `clear` as the confirmed level, as in the data (`hardship_programs.min_hardship_level`); the UI says **"confirmed"**; lowering the flag is called **"clear the flag"** only in code comments, never in the UI | Data enum |
| What counts as a pressure action | `reminder`, `payment_link` and **collection calls** (outbound calls asking for payment). Allowed under hardship: `plan_offer`, `specialist_referral`, `no_contact`, and calls that only offer help | Brief: "flag hardship"; pressure must stop |
| Treatment ladder order | First match wins: (1) hardship possible/confirmed or vulnerable → `specialist_referral` or eligible `plan_offer`; (2) broken promise + payroll delay or cash stress → `plan_offer`; (3) 31+ DPD + high risk → agent call; (4) open promise + high risk + due within 3 days → reminder near payday; (5) open promise + low risk → `no_contact`; (6) otherwise `payment_link` | Removes the ambiguity the spec review found |
| Who changes the hardship flag | Agents and rules raise to `possible`; **only a hardship specialist** confirms (links a program) or lowers it, with a reason. Team leads see the board; they don't change flags | Latch rule |
| Who runs the simulator | Hardship specialists. Agents see eligibility only | Simulator offers above the agent's approver level need a specialist anyway |
| Rows returned by Ask SQL | At most **1,000** rows (the executor's cap). The spec constant `MAX_SQL_ROW_LIMIT` is 1000 | Enough for any chart or table on screen; a larger result is a data pull, not an answer |
| `SELECT *` in Ask SQL | **Refused**, not expanded (`SELECT_STAR_REFUSED` is True) | A star would expose personal columns the role may not see; the analyst names the columns |
| End of the calling window | A call may not **start at or after** the window end: the window is the start time inclusive to the end time exclusive (07:00 to 21:00 in the data's widest case). The gate and the allocator both test `start <= time < end` (`PERMITTED_WINDOW_END_EXCLUSIVE` is True) | One rule in both places, so the plan never schedules a call the gate then blocks |
| Can an agent lower the hardship flag | **No**. Only a hardship specialist, with a reason (`AGENT_MAY_LOWER_HARDSHIP` is False) | Matches the latch in `governance/hardship_latch.py` |
| Can a team lead confirm hardship | **No** (`TEAM_LEAD_MAY_CONFIRM_HARDSHIP` is False). A team lead sees the board and approves batches | Confirming links a program, a specialist task |
| Uses equal to `max_uses_12m` | **Not eligible**: the limit is reached (`USES_EQUAL_TO_MAX_IS_ELIGIBLE` is False); eligible means uses < max | `decisioning/eligibility.py` already tests `uses_12m < max_uses_12m` |
| Single-item approval and the simulator | A hardship specialist may approve an NBA item and run the simulator; a team lead may do neither (batches only); an agent may not run the simulator; only a team lead approves a playbook | These are exactly the decisions the API already enforces (`api/routers/nba.py`, hardship routes) |
| Poor recordings | `asr_confidence_avg` **below 0.80** marks the text features missing (not guessed) in the post-call draft and the text features | v2 rule, now our decision; `features/text_rules.py` |
| Promise check (A2) | Build it: `customer_stated_income_date` is filled on **50%** of promises | Enough coverage |
| Causal claims | Only within **randomly assigned** cases: 146,573 cases (`assignment_method = random`) across champion, challenger_A, challenger_B and a **7,264-case no-contact holdout**. Test cells in rule-based cases are observational | Benchmark questions BQ-014 and BQ-028 rely on this |
| Training history | `account_monthly_snapshot` is **quarter-end** (Dec 2023 to Jun 2026) with dates in **three formats** (`YYYY-MM-DD`, `YYYYMMDD`, `DD/MM/YYYY` or `MM/DD/YYYY`); parse all before use. PTP model labels come from `promises_to_pay` (110,000 kept, 86,820 broken, 7,549 partly kept, 33,005 open) | Profiling |
| Baseline model | The bank's `ptp_break` **v2.1 scores 0.71 AUC** here (the dictionary example said 0.74). Ours must beat it on the same promises | `model_scores` |
| Capacity planning | `channel_capacity` has 98 future rows up to 11 Oct 2026, so the allocator can plan the coming days | Profiling |

## 4. Business value, recomputed

- 2026 volume is about **14,400 new cases a month** (173,357 opened in 2026 to 28 Sep), far above the design's 2,800 estimate.
- The historical **30-day cure rate is about 61%** (2017 to 2025 cohorts). 2026 cohorts read lower (30%) because many are still open: use matured cohorts for the baseline.
- Mean `expected_loss_est` for 2026 cases is **CAD 1,846** (median CAD 91; heavily skewed).
- **+2 points of 30-day cure** ≈ 290 more cures a month. If each avoids a third of the mean expected loss, that's about **CAD 2.1M a year** (was CAD 0.7M in the design). To be refined with matured cohorts and the actual distribution.

## 5. Benchmark (Layer 2)

35 released questions: **21 dev** (gold answers in `labels/benchmark_dev_answers.csv`) and **14 test** (hidden), plus extras at 19:00 on 4 Oct. By type:

| Type | Count (approx.) | Approach |
|---|---|---|
| Metric questions (SQL) | 18 | Certified metrics over silver/gold views; date filters relative to `as_of_date` |
| Policy and procedure questions | 9 | Retrieval over `files/docs/` with precedence (superseded versions are deliberate traps, e.g. a call script v1.0 that says 5 calls a week) |
| Incident questions | 1 | `ops_events` + incident reports (e.g. INC-0923 dialer outage) |
| Call summaries | 3 | Most recent transcript on the case, extractive summary with turn citations |
| Must refuse | 5 | Weather (out of scope), exporting names and phones (PII), gender and marital status, ranking by citizenship, cutting hardship plans by postal area (protected-ground proxy and unfair) |

**Changes:** Ask can start on silver tables before identity resolution finishes. Refusal rules must cover "proxy" requests (FSA-based exclusions), not just named protected attributes.

## 6. Demo customer (shortlist)

Open cases, 31 to 60 DPD, hardship flagged, at least one broken and one open promise, recorded calls, three or more products:

1. **Kirsten Wang** (`CS-2026-879460`, CRM `KIW-6380`): personal loan primary; chequing, mortgage, savings, card; 34 DPD.
2. **Gary James** (`CS-2026-863480`, CRM `GAJ-4280`, London ON): personal loan; card, USD account.
3. **Josette Auger** (`CS-2026-764661`, CRM `JOA-7281`, Québec): personal loan; chequing, card (shows French support).

Final pick after the gold C360 is built (identity must link all their accounts).

## 7. Data issues found so far (feeds the data quality report)

| Issue | Records affected | Handling |
|---|---|---|
| CIF leading zeros lost | 156,837 deposit accounts (64,202 false distinct keys) | `lpad` to 10 digits |
| Mistyped CRM IDs in account snapshots | ~2.6% of 12.6M snapshot rows; 290,000 (account, CRM ID) pairs point to non-existent CRM IDs | Majority vote over valid IDs |
| Mixed snapshot date formats | 837,071 `DD/MM/YYYY` or `MM/DD/YYYY` and 418,081 `YYYYMMDD` rows (of 12.6M) | Parse all formats; disambiguate day/month by the quarter-end rule |
| Duplicate CRM records | 18,496 repeated national ID hashes; 5,950 `duplicate_of_crm_id` | Linked to one golden ID |
| Deleted CRM records | 2,115 `is_deleted = true` | Excluded from survivorship but kept for history |
| Per-system identity formats | All card/loan/deposit/bureau names, DOBs, phones, postal codes (e.g. "C. LIN", "KENNEDY/GARY", "HAAS E O"; DOB as `24-07-1969`, `1983/01/31`, `19890531`; masked phones `780304xxx63`) | Per-source parsers before matching |
| Bureau file with a shifted column (DFI-0812) | About 10,000 subjects (ops estimate) | To profile: detect and exclude affected pulls |
| Schema drift `channel` → `channel_v2` (REL-0926) | contact_history rows after 26 Sep | Coalesce |
| App outage with wrong late fees (INC-0914) | About 1,900 customers (ops estimate) | Exclude from model labels; caveat in Ask; H5 candidate list |
