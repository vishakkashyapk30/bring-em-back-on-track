# Model card: promise-to-pay break model (`ptp_break`, ours)

> **Status: trained and evaluated** (3 to 4 Oct 2026). Numbers come from `reports/model_eval.json`, written by `python -m models.ptp_break.train`. Structure follows OSFI E-23 model-risk expectations.

| | |
|---|---|
| Owner | Collections Analytics (team Deep in Debt for the hackathon) |
| Purpose | Rank open promises to pay by the chance they break, to inform the NBA treatment ladder. **Not** a credit decision |
| Use in decisions | One input to a rule-based treatment ladder, after the policy gate. A person approves every customer-facing action |
| Label | Promise broken or partly kept after due date + grace days = 1; kept = 0; open/cancelled excluded; promises overlapping a payment-posting outage excluded |
| Data | `promises_to_pay` + point-in-time features from the feature store (`features/registry.yaml`) |
| Algorithm | LightGBM (monotone constraints on prior broken promises, days past due, complaints and disputes), isotonic calibration, then a logistic blend with the bank's v2.1 score; TreeSHAP top-3 reason codes |
| Split | Time-based on the date the promise was made: train before 1 Apr 2026 (121,975 promises), calibration and blend fitting Apr to Jun 2026 (24,846), test Jul to Sep 2026 (56,935) |
| Baseline | Bank's `model_scores` `ptp_break` v2.1 (the data dictionary says AUC 0.74; on our test promises it is 0.694) on the same promises |

## Performance (Jul to Sep 2026, the 25,617 test promises that v2.1 also scored)

| Metric | Bank v2.1 | Ours alone | **Blend (used)** |
|---|---|---|---|
| AUC | 0.694 | 0.666 | **0.744** |
| Brier score (lower is better) | 0.230 | 0.224 | **0.195** |
| Precision @ top 10% | 0.861 | 0.822 | 0.920 |
| Recall @ top 10% | 0.138 | 0.131 | 0.147 |
| Lift @ top 10% | 1.375 | 1.313 | 1.469 |

The base rate of broken promises in this period is 62.6%, so precision at the top 10% is high for every model and lift is the fairer comparison. On all 56,935 test promises (including those v2.1 did not score) our model alone has AUC 0.656 and Brier 0.219.

**Decision taken:** our model alone does not beat v2.1 on ranking (AUC 0.666 against 0.694), so by the rule below we do not replace it. A logistic blend of the two scores, fitted on the Apr to Jun calibration period and judged on Jul to Sep, beats both on every metric. The app scores the 33,005 open promises with the blend. Blend weights on the logit scale: v2.1 0.60, ours 0.93, intercept 0.77.

**Why ours alone is weaker than a model "should" be.** The first version scored AUC 0.95. That was leakage: in this release the promised amount looks back-filled after the outcome (69% of kept promises are for the full overdue amount, against 0.3% of still-open ones). `ptp_amount` and `ptp_to_overdue_ratio` are excluded, and training stops with an error if test AUC goes above 0.90. Also excluded: the case queue (current state, not as of the promise), entry days past due (constant 1) and due date minus stated payday (constant 0). The honest signal is modest, and the strongest drivers are days between creation and due date, days past due at creation, hardship language in the transcripts and notes, and time in the case.

**Calibration (blend).** Close to the diagonal in the upper bins; the model under-predicts breaks in the latest quarter by 3.6 points overall (predicted bin 0.0 to 0.1 observed 0.13; bin 0.2 to 0.3 observed 0.32), worst for vulnerable customers (see Fairness). Calibration is by overall period, not by segment.

**Fallback.** A promise the bank did not score is scored by our calibrated model alone and labelled `our model (no bank v2.1 score)` on the row. Today every one of the 33,005 open promises has a v2.1 score, so the fallback is used 0 times. The same fallback applies to 31,318 of the 56,935 test promises, which is why the all-promise figure above is lower.

**Decision rule:** if ours does not beat v2.1, NBA uses v2.1 scores (or the blend when the blend beats both) and this card says so.

## Fairness

Excluded inputs: the 12 protected attributes, age, age band and voice acoustics. Audit: `python -m governance.fairness.report` writes `reports/fairness.json`, shown on Governance > Fairness. Only `governance/fairness/` reads the protected attributes (auditor view); nothing else may.

**Proxy test** (60,000 customers, 5-fold cross-validated logistic model per feature group, nine attributes): no feature group reaches the 0.65 line. Highest is 0.58, text signals predicting vulnerability type (vulnerable customers do talk about hardship more, which is the signal working as intended). All five groups (promise terms, delinquency, contact history, text signals, cash stress) stay.

**Outcome test** (56,935 promises due Jul to Sep 2026, by gender, age band, marital status, citizenship, newcomer, accessibility needs, vulnerability type, household size and dependants). The score runs 3.6 points below the real break rate in this quarter overall. A group goes to review when its gap differs from that by more than 3 points, or its high-risk flag rate is outside 0.8x to 1.25x of everyone's. Six groups were flagged:

- Five vulnerability types (financial hardship, serious illness, mental health, domestic situation, natural disaster): they break 72 to 75% of promises against 63% for others, are flagged 1.10 to 1.17 times as often, are under-predicted by a further 3.5 to 3.9 points, and get more false alarms (56 to 67% against 46%).
- Age 65 and over: over-predicted by 4 points beyond the overall gap, flag rate in line (0.995x).

**What we conclude.** The higher flag rate for vulnerable customers follows their real break rate, so it is not unfair scoring by itself. The risk is in what happens next, so the rule is: a high break risk can add a reminder or a person's follow-up, and it can never raise pressure; the policy gate and hardship latch run first. We confirm this on the next-best-action decisions once they exist for the test period (action, pressure and contact rates by group), and recalibrate by segment if the gap persists. Groups with fewer than 300 promises are shown as low volume and not judged; groups under 10 customers are hidden.

## Limitations

Synthetic data; text features only for transcribed calls (~1% of contacts); scores are model estimates, not causal effects of any treatment.
