# Row scope by role

Who may open which case, customer or call. It is decided in the API (`api/access.py`) and in Ask (`api/services/ask_access.py`, `common/ask_scope.py`) before any data is read, and it is the same in rules mode and language-model mode. When the app serves sample data (no warehouse) nothing is enforced.

| Role | Rule |
|---|---|
| Agent | Cases where `collections_cases.assigned_agent_id` is the agent, and the customers and calls on those cases. |
| Team lead | Cases where `assigned_team` is the lead's team. |
| Hardship specialist | A case is open when any of the four conditions below holds. |
| Steward | Data quality, identity queue, drift and feature screens, and a customer's identity lineage (source keys, method, confidence). Never an individual customer's record, contact history, calls, notes or call summaries. |
| Analyst | Aggregates only (unchanged). |

## Hardship specialist rule

The specialist opens a case, its customer and its calls only when:

1. the case is assigned to them (`assigned_agent_id`) or to their team (`assigned_team`);
2. the case itself is flagged hardship (`hardship_flag`) or vulnerable (`vulnerable_customer_flag`);
3. the customer is on the hardship board or flagged at customer level (`gold.c360_customer.hardship_flag` is `possible` or `clear`, or `vulnerability_flag`); the board is exactly the customers with `possible` and an open case;
4. the customer's latest `hardship_flag_events` row in the ops store is not `none` (flagged since the last nightly build).

Anything else is refused with a 403 and the reason "This case is not on the hardship board, not flagged hardship or vulnerable, and not assigned to you or your team." Protected attributes are never used.

## Where it applies

* API: `access.case`, `access.golden`, `access.contact` (NBA, what-if, eligibility, customer, timeline, features, calls, voice); the assistant tools and the LLM agent call the same functions.
* Stewards: `access.individual` refuses `/customers/{id}` and `/customers/{id}/timeline`; `/customers/{id}/identity` uses `access.lineage` and stays open.
* Ask: `scope_for("hardship_specialist", ...)` applies rule 1 to 4 to every case id (call summaries and interaction search); `scope_for("steward", ...)` refuses all individual calls, notes and summaries.
* Web: the customer page shows the refusal reason, and for stewards the identity lineage underneath.
