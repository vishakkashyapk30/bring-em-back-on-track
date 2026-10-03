# Model card: promise-to-pay break model (`ptp_break`, ours)

> **Status: template.** Filled after training (`models/ptp_break/evaluate.py` writes the numbers). Structure follows OSFI E-23 model-risk expectations.

| | |
|---|---|
| Owner | Collections Analytics (team Deep in Debt for the hackathon) |
| Purpose | Rank open promises to pay by the chance they break, to inform the NBA treatment ladder. **Not** a credit decision |
| Use in decisions | One input to a rule-based treatment ladder, after the policy gate. A person approves every customer-facing action |
| Label | Promise broken or partly kept after due date + grace days = 1; kept = 0; open/cancelled excluded; promises overlapping a payment-posting outage excluded |
| Data | `promises_to_pay` + point-in-time features from the feature store (`features/registry.yaml`) |
| Algorithm | LightGBM with monotone constraints, isotonic calibration; SHAP top-3 reason codes |
| Split | Time-based: train to Mar 2026, validate Apr–Jun, test Jul–Sep (TBC after profiling) |
| Baseline | Bank's `model_scores` `ptp_break` v2.1 (AUC 0.74 at validation) on the same test promises |

## Performance (test period, same promises as v2.1)

| Metric | Ours | v2.1 |
|---|---|---|
| AUC | TBC | TBC |
| Brier score | TBC | TBC |
| Precision / recall @ top 10% | TBC | TBC |
| Lift @ top 10% | TBC | TBC |

**Decision rule:** if ours does not beat v2.1, NBA uses v2.1 scores and this card says so.

## Fairness

Excluded inputs: the 12 protected attributes, age, age band and voice acoustics. Audit: `python -m governance.fairness.report` writes `reports/fairness.json`, shown on Governance > Fairness. Only `governance/fairness/` reads the protected attributes (auditor view); nothing else may.

**Proxy test** (60,000 customers, 5-fold cross-validated logistic model per feature group, nine attributes): no feature group reaches the 0.65 line. Highest is 0.58, text signals predicting vulnerability type (vulnerable customers do talk about hardship more, which is the signal working as intended). All five groups (promise terms, delinquency, contact history, text signals, cash stress) stay.

**Outcome test** (56,935 promises due Jul to Sep 2026, by gender, age band, marital status, citizenship, newcomer, accessibility needs, vulnerability type, household size and dependants). The score runs 3.6 points below the real break rate in this quarter overall. A group goes to review when its gap differs from that by more than 3 points, or its high-risk flag rate is outside 0.8x to 1.25x of everyone's. Six groups were flagged:

- Five vulnerability types (financial hardship, serious illness, mental health, domestic situation, natural disaster): they break 72 to 75% of promises against 63% for others, are flagged 1.10 to 1.17 times as often, are under-predicted by a further 3.5 to 3.9 points, and get more false alarms (56 to 67% against 46%).
- Age 65 and over: over-predicted by 4 points beyond the overall gap, flag rate in line (0.995x).

**What we conclude.** The higher flag rate for vulnerable customers follows their real break rate, so it is not unfair scoring by itself. The risk is in what happens next, so the rule is: a high break risk can add a reminder or a person's follow-up, and it can never raise pressure; the policy gate and hardship latch run first. We confirm this on the next-best-action decisions once they exist for the test period (action, pressure and contact rates by group), and recalibrate by segment if the gap persists. Groups with fewer than 300 promises are shown as low volume and not judged; groups under 10 customers are hidden.

## Limitations

Synthetic data; text features only for transcribed calls (~1% of contacts); scores are model estimates, not causal effects of any treatment.
