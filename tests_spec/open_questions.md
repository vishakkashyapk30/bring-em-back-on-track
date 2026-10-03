# Open questions for the design team

These are ambiguities and contradictions found while writing the specification tests. Where V1 (`collections_system_design_V1.md`) and v2 (`collections_system_design_v2.md`) differ, **the suite follows V1, the primary spec**, and says so below. Each item names the constant in `tests_spec/spec_constants.py` that encodes the current assumption. When a constant is `None`, the dependent test skips until you resolve it.

Doc abbreviations: **Brief** = problem statement and challenge brief; **V1** / **v2** = system design versions; **NI** = novel ideas register.

## Top five (resolve first)

| # | Question | Why it matters |
|---|---|---|
| Q2 | **What does the hardship level `clear` mean?** V1 §10, v2 §9 and the contract use `none / possible / clear`, where `clear` is the *highest* level (a specialist "confirms" to it). But V1 §8 says "Only a person can **clear** a hardship flag", using *clear* as a verb meaning *lower*. The Brief's online vector has `hardship_signal: "clear"` for Ryan. | One word means both "confirmed hardship" and "no hardship". A developer could easily treat `clear` as "lowered" and switch pressure back on. The tests read `clear` as confirmed (the highest level). Consider renaming it to `confirmed`. |
| Q3 | **Which treatments are "pressure actions"?** V1 §6 step 1, V1 §2 and v2 §2 all say a hardship or vulnerability flag "removes pressure actions", but the term is never defined. Is an outbound agent call pressure? Is a payment link? | The "pressure on hardship = 0" guardrail can't be measured without a definition. Assumed: `PRESSURE_TREATMENTS = {reminder, payment_link}`; non-pressure = `plan_offer`, `specialist_referral`, `no_contact`. |
| Q1 | **Sundays: is `sunday_contact_permitted` honoured?** V1 §6 step 1: "never Sundays or holidays". v2 §6 step 1: "off Sundays unless `sunday_contact_permitted`". | This is a direct contradiction in a compliance rule. The suite follows V1 (`SUNDAY_FLAG_UNLOCKS_SUNDAY_CALLS = False`). |
| Q4 | **What is the ladder precedence when rules overlap?** V1 §6 step 3 lists four rules (low-risk -> no contact; high risk and due within 3 days -> reminder; broken promise with late pay -> plan offer; over 30 DPD and high risk -> agent call). Ryan, the demo customer, matches several at once: 38 DPD, a broken promise, pay 29 days late, and an open promise due within 3 days. | Without an order the NBA for the demo customer is undefined. The ladder tests only check each rule on its own. Ryan's journey tests only assert "no pressure" (because of the hardship flag), not a specific treatment. |
| Q5 | **Which roles may confirm, lower or approve?** "Only a person can lower" the flag (V1 §10). Can a front-line agent lower it, or only a hardship specialist? Can a team lead confirm? Who may run the simulator ("A specialist can try", V1 §6 UC3)? v2 says `approver_level` is "hardship specialist or team lead"; V1 only says "a higher approver". | Role-based access tests need a permission matrix. Unknown cells are `None` (they skip): `AGENT_MAY_LOWER_HARDSHIP`, `TEAM_LEAD_MAY_CONFIRM_HARDSHIP`, and some `MATRIX` cells in `system/test_rbac.py`. |

## Contact policy gate

- **Q7 Permitted hours.** (a) Which channels does the hours rule cover? v2 says "Calls only inside ..."; V1 just says "permitted hours". The suite tests calls only (`HOURS_RULE_CHANNELS`). (b) Is the end of the window exclusive (is 20:00 allowed)? `PERMITTED_WINDOW_END_EXCLUSIVE = None`. (c) Which holiday calendar applies, national or provincial (for example Thanksgiving, or Family Day in only some provinces)? The tests use only Canada Day and Christmas Day.
- **Q8 Weekly contact limit.** Is it a rolling 7 days (`contact_cap_7d`, v2) or a calendar week ("3 of 3 contacts used this week")? Does it count all channels or calls only? Attempts or connected contacts? The suite tests calls against a per-customer cap.
- **Q15 Representatives and block precedence.** The contract maps `credit_counselling_agency_flag` and `legal_representative_flag` to `contact_block = represented`, while v2 uses `third_party_rep_flag`. The gate "sends the case to a person" (V1). Can that person contact the representative through the system? `contact_block` is one enum value, so if a customer is both deceased and has a cease request, which value wins?
- **Q16 Dispute scope.** V1 says a dispute "pauses it" (the case). v2 says the "account pauses". For a customer with several accounts, are the other accounts still contactable?
- **Q19 Marketing-only flags.** Only v2 says the gate ignores `national_dncl_flag` and CASL consent. V1 is silent. The suite assumes the v2 statement still holds.
- **Q26 "Customers not yet behind".** This needs Policy Office sign-off (V1 §6 and the contract). Is it DPD = 0, no open case, or both?

## Hardship, eligibility, simulator

- **Q6 Demo step 4 vs the card rule.** NI §8 step 4 has the specialist try "a 3-month cut, then a term extension" for Ryan, but Ryan's delinquent product is the card (his loan is current), and V1 §6 UC3 says "Cards only get a lower payment". Whether `hardship_programs.product_types` covers cards at all is TBC. The suite follows V1: a term extension on the card is refused (`rejected_levers`).
- **Q11 Eligibility edges.** Is `dpd == max_dpd` eligible? Is `months_on_book == min` eligible? Is a customer who already used `max_uses_12m` eligible? (All `None` or assumed in constants.) Is `min_hardship_level` (v2) an eligibility rule? V1 lists only five rules. Is `requires_income_evidence` a pass/fail rule, or only shown?
- **Q24 Deriving the hardship flag.** The contract derives the `none / possible / clear` enum from `collections_cases.hardship_flag` (a boolean?), `hardship_mentioned_flag` and `hardship_signal`. What is the mapping? The suite assumes that any mention means at least `possible`.
- **Q33 Card program coverage and the 0% rate.** Is `rate_override = 0` allowed (NI H1, TBC)?

## NBA and models

- **Q14 Reminder timing.** V1 sends the reminder "in the window nearest the next payday, if that beats the bank's current timing scores". v2 uses "the existing timing slot (`model_scores.slot_rank = 1`)". Which is the Phase 1 default?
- **Q20 Payday reference in A2.** Is "days before payday" measured to `customer_stated_income_date` or to `expected_next_payroll_date`? The fixtures make the two equal, so either reading passes.
- **Q22 Uplift gate edges.** Is exactly 70% overlap, or exactly 1,000 cases, enough? The suite assumes yes (inclusive). Is "comparable history" the v2 propensity band [0.05, 0.95]?
- **Q28 "Off-strategy actions"** must be reviewed one by one (V1 §6), but the term is not defined.
- **Q30 "What has changed"** in the explanation: changed since when? The last decision, or the last contact?
- **Q-risk Risk cut-offs.** "Low risk" and "high risk" thresholds are not given. Tests use only extreme probabilities (0.02 and 0.97).
- **Q-mono Monotone features.** "More late payments never lower the risk": which features exactly? Assumed: `ptp_broken_count_90d`, `dpd_max_current`.

## Human review and audit

- **Q9 Batch sample.** For "2% checked first": how is the sample rounded (assumed ceil, at least 1)? Who checks it? What happens to the batch if a sampled item is wrong?
- **Q25 Override reason.** Is a reason mandatory? V1: "anything can be overridden"; v2: "override and edit reasons feed monitoring". The suite assumes a reason is required.
- **Q18 Engineer vs data steward.** S3 drift fixes are approved by "an engineer". The five roles (V1 §10) have no engineer; the contract steward is the "Collections Data Engineering lead". The suite assumes the data steward role approves drift fixes.

## Layer 1 and the contract

- **Q12 Identity rules.** v2 sends clusters with "any internal pair below 0.5" to review; V1 dropped this. Is it still a rule? Is the `national_id_hash` salt shared across sources (TBC in both)? What is the numeric auto-merge cut-off that contract rule 2 refers to?
- **Q13 Employer features are V1-only.** `employer_key`, contract quality rule 10 and the "employer radar" consumer appear only in V1. The 90% match-rate threshold is TBC.
- **Q31 Golden ID format.** The Brief shows `G-004817`. Is this format a requirement? The suite never asserts an exact ID.
- **Q-retention** The retention period is "TBC" in both contracts.

## Layer 2

- **Q10 SQL guard limits.** What is the maximum row limit (`MAX_SQL_ROW_LIMIT = None`)? Is `SELECT *` refused, or expanded to allowed columns (`SELECT_STAR_REFUSED = None`)?
- **Q17 Analyst access to individual customers.** The contract says `display_name` is "masked for analysts", which implies analysts can see individual rows. v2 §4 says analysts see "aggregates with groups under 10 suppressed". The suite accepts either masking or denial.
- **Q27 Benchmark size.** The number of benchmark questions and transcripts is "[__]" in the Brief. Benchmark accuracy can't be specified until it is known.

## Data, features, metrics

- **Q21 Cure rate.** Do held (insolvency or deceased) cases leave the denominator as well as the numerator? The suite assumes yes. How are cases opened less than 30 days ago counted?
- **Q23 ASR threshold.** `asr_confidence_avg < 0.80` is in v2 only (TBC). V1 just says "poor recordings count as missing".
- **Q29 Layer count (no conflict).** Part 2 of the Brief shows three layers; Part 1 and the design use four. The suite follows four.
