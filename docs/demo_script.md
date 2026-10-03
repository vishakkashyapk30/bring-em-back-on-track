# Demo script for judges (5 minutes)

Open `/demo` signed out. It shows no data, only the five personas. Each persona runs a guided tour of 7 stages plus a recap, on one real synthetic customer (J. Tyler) with live numbers. Use the left and right arrow keys to move, and "Open the real screen" to jump into the product (a banner brings you back).

## Order and timing

1. Collections agent (90 s): the everyday story and the guardrails.
2. Hardship specialist (60 s): the human decides, with a reason.
3. Team lead (60 s): batch approval and the stress test.
4. Strategy analyst (50 s): certified metrics, a refusal, honest model numbers.
5. Data steward (40 s): identity, quality and the audit log.

Skip stages you have shown before. Finish by clicking "Run the assistant on this customer" on any recap.

## Collections agent: An agent's day with one customer

| Stage | Say | Click |
|---|---|---|
| Today's queue | The queue is ranked by risk, and every row says why. | Next |
| Customer 360 and identity | One view built from five source records; the constellation shows how sure each match is. | Next |
| Next best action and the policy gate | The contact rules run before any model. Hardship removes pressure actions. | Open the real screen |
| Program eligibility | Offers are checked against program rules, not guessed. | Next |
| Promise check against payday | A promise due before payday is likelier to break. This is a model estimate, not cause and effect. | Next |
| Call summary | Notes are drafted from the call and wait for the agent. | Next |
| Approve, edit or override | A person decides; an override needs a reason. | Recap, then the assistant |

## Hardship specialist: A hardship specialist's review of one customer

| Stage | Say | Click |
|---|---|---|
| Review board | Everyone flagged, in one place. | Next |
| Missed offers | Customers who qualified but were not offered a program. | Next |
| The customer | Same customer, specialist's view. | Next |
| Eligibility rules | Program limits are applied in code. | Next |
| Plan simulator | Try a plan; nothing is saved. | Open the real screen |
| Approver level | Bigger plans need a higher approver. | Next |
| Confirm or lower the flag, with a reason | The flag is a latch: only a person can lower it, with a reason on the audit log. | Recap |

## Team lead: A team lead's morning

| Stage | Say | Click |
|---|---|---|
| Team queue | The team's work today. | Next |
| Batch queue and the 2% sample | Routine reminders go in batches; a sample is checked first. | Next |
| Stress test: dialer down | What if call capacity drops? Planning note only. | Next |
| Override rate and guardrails | Overrides are watched, not hidden. | Next |
| Team load | Who has how much. | Next |
| Spot-check one case | Any case opens with its full reasoning. | Next |
| Approve the batch | The lead approves; the system never sends on its own. | Recap |

## Strategy analyst: An analyst's questions

| Stage | Say | Click |
|---|---|---|
| A certified metric question | Questions are answered from certified metrics, with the SQL shown. | Next |
| Roll rate | Same, for roll rate. | Next |
| Map | Postal area is shown for information, never used to treat customers differently. | Next |
| Scorecard, honest about causality | Observed numbers and randomised numbers are labelled differently. | Next |
| A refused question | Asking to rank by citizenship is refused, with the reason. | Next |
| Model card | Real AUC against the bank's v2.1, labelled as model estimates. | Next |
| Fairness | Proxy tests and outcome gaps that need human review. | Recap |

## Data steward: A data steward's checks

| Stage | Say | Click |
|---|---|---|
| Identity review queue | Uncertain matches wait for a person. | Next |
| Match confidence and lineage | Every source key behind one customer. | Next |
| Data quality report | Checks with pass or fail counts. | Next |
| Contract tests | The data contract is tested every night. | Next |
| Feature parity | Training and serving agree. | Next |
| Freshness | How old the data is. | Next |
| Audit log | Every decision, append only. | Recap |

## Three things to point out

1. Guardrails: the policy gate runs before any model, protected attributes are never used, and refused questions explain why. The assistant for an agent never offers hardship or team tools.
2. Human in the loop: the assistant only proposes. Each proposal links to the existing screen, and says "Nothing is sent or changed until you approve it there." Every run gets an audit number.
3. Honest model numbers: estimates are labelled as model estimates, observed and randomised results are kept apart, and the assistant works with no language model (rules mode), with a language model optional.
