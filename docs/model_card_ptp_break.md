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

Excluded inputs: the 12 protected attributes, age, age band and voice acoustics. Proxy test and outcome tests by group: TBC (`governance/fairness/`).

## Limitations

Synthetic data; text features only for transcribed calls (~1% of contacts); scores are model estimates, not causal effects of any treatment.
