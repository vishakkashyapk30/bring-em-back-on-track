# Model card: promise-to-pay break model (`ptp_break`, ours)

> **Status: trained and evaluated** (3 to 4 Oct 2026). Numbers come from `reports/model_eval.json`, written by `python -m models.ptp_break.train`. Structure follows OSFI E-23 model-risk expectations.

| | |
|---|---|
| Owner | Collections Analytics (team Deep in Debt for the hackathon) |
| Purpose | Rank open promises to pay by the chance they break, to inform the NBA treatment ladder. **Not** a credit decision |
| Use in decisions | One input to a rule-based treatment ladder, after the policy gate. A person approves every customer-facing action |
| Label | Promise broken or partly kept after due date + grace days = 1; kept = 0; open/cancelled excluded; promises overlapping a payment-posting outage excluded |
| Data | `promises_to_pay` + 44 point-in-time features from the feature store (`features/registry.yaml`): promise terms, case and contact history, text signals from notes and calls, and (added 4 Oct) credit and account history as of the promise: the latest bureau pull, salary credits in the three months before, the last card statement already due and the last month-end account snapshot |
| Algorithm | LightGBM (monotone constraints: more prior broken promises, days past due, complaints, disputes, delinquent bureau trades, missed salary months or delinquent card cycles never lower the risk), isotonic calibration, then a logistic blend with the bank's v2.1 score; TreeSHAP top-3 reason codes |
| Split | Time-based on the date the promise was made: train before 1 Apr 2026 (121,975 promises), calibration and blend fitting Apr to Jun 2026 (24,846), test Jul to Sep 2026 (56,935) |
| Baseline | Bank's `model_scores` `ptp_break` v2.1 (the data dictionary says AUC 0.74; on our test promises it is 0.694) on the same promises |

## Performance (Jul to Sep 2026, the 25,617 test promises that v2.1 also scored)

| Metric | Bank v2.1 | Ours alone | **Blend (used)** |
|---|---|---|---|
| AUC | 0.694 | 0.712 | **0.772** |
| Brier score (lower is better) | 0.230 | 0.206 | **0.184** |
| Precision @ top 10% | 0.861 | 0.806 | 0.916 |
| Recall @ top 10% | 0.138 | 0.129 | 0.146 |
| Lift @ top 10% | 1.375 | 1.287 | 1.463 |

The base rate of broken promises in this period is 62.6%, so precision at the top 10% is high for every model and lift is the fairer comparison. Ours alone ranks better overall than v2.1 (AUC 0.712 against 0.694) but is weaker at the very top of the list (precision 0.806 against 0.861); the blend wins on every metric. On all 56,935 test promises (including those v2.1 did not score) our model alone has AUC 0.690 and Brier 0.207. Fitting the whole LightGBM model takes about 2 seconds on a laptop CPU (266 trees).

**Decision taken:** ours alone now beats v2.1 on AUC and Brier, but not on precision at the top decile, and the blend beats both on all of them. A logistic blend of the two scores, fitted on the Apr to Jun calibration period and judged on Jul to Sep, is what the app uses for the 33,005 open promises. Blend weights on the logit scale: v2.1 0.59, ours 0.92, intercept 0.45.

**How the number moved (and what did not help).**

1. The first honest model, on promise terms, case and contact history and text signals, scored AUC 0.666 (blend 0.744). The first version had scored 0.95, which was leakage: in this release the promised amount looks back-filled after the outcome (69% of kept promises are for the full overdue amount, against 0.3% of still-open ones). `ptp_amount` and `ptp_to_overdue_ratio` are excluded, and training stops with an error if test AUC goes above 0.90. Also excluded: the case queue (current state, not as of the promise), entry days past due (constant 1) and due date minus stated payday (constant 0).
2. A better algorithm did not help. Six variants (LightGBM shallow, deep, regularised and extra-trees, scikit-learn gradient boosting, logistic regression) all landed between AUC 0.649 and 0.656 on all test promises (0.660 to 0.669 on the v2.1 subset), and stacking them with the bank score added +0.002 (0.7434 to 0.7452). The ceiling was the information in the features, not the model.
3. New information helped: 18 features from the bureau, salary credits, card statements and month-end snapshots, each joined strictly as of the promise date, lifted ours alone from 0.667 to 0.712 and the blend from 0.744 to 0.772. Each group helped on its own (bureau +0.026, card statements +0.026, account snapshot +0.022, salary +0.012).
4. **A leak caught on the way.** The first card feature, `days_late`, looked like the strongest signal (with it the model scored 0.718). It comes from the first payment after the due date, which can fall after the promise. Making it point in time (use it only when that payment had already happened) cut its importance from 49,000 to 4,600 and the AUC to 0.713. Statements are also taken only once their due date has passed, and salary credits only from whole months before the promise.

The strongest drivers now are days between creation and due date, days past due at creation, card utilisation on the last statement, hardship language in the transcripts and notes, days in the case, and bureau utilisation.

**Calibration (blend).** Predicted and observed break rates are within about 6 points in every band; the model under-predicts a little in the middle bands (0.3 to 0.7) and is close in the top bands. Overall it predicts 62.3% against 64.3% observed (2.0 points low, from 3.6 before the new features). Calibration is by overall period, not by segment.

**Fallback.** A promise the bank did not score is scored by our calibrated model alone and labelled `our model (no bank v2.1 score)` on the row. Today every one of the 33,005 open promises has a v2.1 score, so the fallback is used 0 times. Because ours alone now beats v2.1 on AUC, the fallback is a reasonable model rather than a stopgap. The all-promise figure above is lower than the head-to-head figure because it includes the 31,318 test promises v2.1 did not score.

**Decision rule:** if ours does not beat v2.1, NBA uses v2.1 scores (or the blend when the blend beats both) and this card says so.

## Fairness

Excluded inputs: the 12 protected attributes, age, age band and voice acoustics. Audit: `python -m governance.fairness.report` writes `reports/fairness.json`, shown on Governance > Fairness. Only `governance/fairness/` reads the protected attributes (auditor view); nothing else may.

**Proxy test** (about 53,000 customers, 5-fold cross-validated logistic model per feature group, nine attributes): no feature group reaches the 0.65 line. The gate is automatic: a group above 0.65 for any protected attribute is dropped from the model input (training leaves its columns out and the training report lists them under `dropped_by_proxy_gate`) and is also sent to a person for review with the numbers. Nothing is dropped today. Highest is 0.58, the new credit history group (bureau, salary, card and account history) and the text signals both predicting vulnerability type (vulnerable customers do talk about hardship more and carry more credit stress, which is the signal working as intended). All six groups (promise terms, delinquency, contact history, text signals, credit history, cash stress) stay.

**Outcome test** (56,935 promises due Jul to Sep 2026, by gender, age band, marital status, citizenship, newcomer, accessibility needs, vulnerability type, household size and dependants). The score runs 2.0 points below the real break rate in this quarter overall (3.6 before the credit-history features). A group goes to review when its gap differs from that by more than 3 points, or its high-risk flag rate is outside 0.8x to 1.25x of everyone's. Three groups were flagged (six before):

- Two vulnerability types, mental health and natural disaster: they break 72 to 75% of promises against 63% for others, are flagged 1.16 and 1.20 times as often, are under-predicted by a further 3.0 and 3.5 points, and get more false alarms (57 and 64% against 42%). The other three vulnerability types sit just inside the review limits.
- Age 65 and over: over-predicted by 4.1 points beyond the overall gap, flag rate in line (0.99x).

**What we conclude.** The higher flag rate for vulnerable customers follows their real break rate, so it is not unfair scoring by itself. The risk is in what happens next, so the rule is: a high break risk can add a reminder or a person's follow-up, and it can never raise pressure; the policy gate and hardship latch run first. We confirm this on the next-best-action decisions once they exist for the test period (action, pressure and contact rates by group), and recalibrate by segment if the gap persists. Groups with fewer than 300 promises are shown as low volume and not judged; groups under 10 customers are hidden.

**NBA decisions by group** (`python -m governance.fairness.nba_rates`, `reports/fairness_nba.json`, `docs/reference/fairness_nba.md`, Governance > Fairness > NBA decisions). Measured on the 86,058 open cases of the 28 Sep 2026 queue (51,002 scheduled): action mix, pressure, contact, no-contact and hardship or vulnerable routing rates, mean break risk and mean expected value, by every audited attribute, with the same 0.8x to 1.25x line and a 300-case minimum. The design claim holds: of 39,022 hardship or vulnerable cases, 0 were given a pressure action, and re-deciding each of them at a break risk of 0.05 and 0.95 never turned pressure on (0 violations). Six groups are flagged: the five largest vulnerability types (pressure 0.00x and routing about 2.2x, which is the gentler treatment by design) and marital status separated (pressure 0.73x, routing 1.37x, which needs a person to confirm it follows their higher hardship and vulnerability share and not the score).

## Limitations

Synthetic data; text features only for transcribed calls (~1% of contacts); scores are model estimates, not causal effects of any treatment.
