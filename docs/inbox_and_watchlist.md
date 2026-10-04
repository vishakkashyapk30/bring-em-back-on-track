# Inbox and watchlist

Two features that help each person keep track of their work. They add no new approval logic.

* **Waiting for you** (`/inbox`): one list per persona of every pending human review in the system. Each item says what it is, why it needs you (in plain English), how long it has waited or when it is due, and links to the existing screen where you act on it. The inbox only reads.
* **Saved watchlist**: pin a customer, case, agent, employer, cohort, data product or identity to follow it. The signed-in home shows what changed since you last looked.

## Endpoints

| Method and path | Roles | Purpose |
|---|---|---|
| `GET /api/inbox` | all | Groups of pending items in your row scope, the 3 most urgent (`top`), and `not_available` (sources that can't be read, with the reason) |
| `GET /api/inbox/counts` | all | `{total, by_type}` for the nav badge (cached for 20 seconds per person) |
| `GET /api/watchlist` | all | Your pins, each with `status` (the facts now), `changes` (since `last_seen_at`), `link` (the existing screen) and `track_link` (`/track/<kind>/<id>`) |
| `GET /api/watchlist/pins` | all | Just the pinned `(kind, subject_id)` pairs, for the watch buttons |
| `POST /api/watchlist` | all | `{kind, subject_id, label?}`: pin. 403 if you may not open the subject. Audited (`watch_pin`) |
| `DELETE /api/watchlist/{kind}/{subject_id}` | all | Unpin. Audited (`watch_unpin`) |
| `POST /api/watchlist/{kind}/{subject_id}/seen` | all | Mark as looked at: the facts now become the baseline for the next "what changed" |

Code: `api/routers/inbox.py`, `api/services/inbox.py`, `api/schemas/inbox.py`, `api/routers/watchlist.py`, `api/services/watchlist.py`, `api/schemas/watchlist.py`. Frontend: `web/src/pages/Inbox.tsx`, `web/src/components/WatchButton.tsx`, `web/src/components/HomePanels.tsx`, `web/src/api/inbox.ts`.

## What each persona sees in the inbox

Every source reads the same store as the screen it links to, with the same row scope (`docs/row_scope.md`).

| Persona | Group | Source | Links to |
|---|---|---|---|
| Agent | Next best actions to review | Nightly queue, your cases (`assigned_agent_id`), one-by-one review, scheduled, no decision yet in `nba_decisions` | `/customers/<id>` |
| Agent | Call summaries to approve | Transcripts on your cases in the 14 days before the data date, not yet approved in `call_summaries` | `/calls/<contact_id>` |
| Agent | Promises due soon with a high break risk | `ptp_scores.parquet`, your cases, due in the next 7 days, band high or very high | `/customers/<id>` |
| Hardship specialist | Possible hardship to confirm or clear | The review board (`hardship.board`), with the 5-business-day review deadline, plus flags raised to `possible` in the app since the nightly build | `/hardship/board` |
| Hardship specialist | Vulnerability reviews due | `vulnerability_flag` with a review date today or past (never `vulnerability_type`) | `/hardship/board` |
| Hardship specialist | Cases routed to a hardship specialist | Nightly queue, `route_to = hardship_specialist` at your site, no decision yet | `/customers/<id>` |
| Hardship specialist | Missed hardship offers | `hardship.missed_offers` (first 50) | `/hardship/missed` |
| Team lead | Batches to approve | `batches` pending for your team, with the 2% sample size | `/team` |
| Team lead | Playbook proposals | `playbook_proposals` pending (radar, outage refunds, regional) | `/team?tab=playbooks` |
| Team lead | Overrides above the review threshold | Agents on your team with more than 25% of at least 5 decisions changed (`governance.monitoring.override_rate`) | `/governance/monitoring` |
| Team lead | Strategy tests proposed by analysts | Pending `strategy_test` proposals in the playbook store (from the Track pages), and a `proposals` table if one exists | `/team?tab=playbooks` |
| Analyst | Your proposals (shown, not counted) | Your own strategy-test proposals and their status. Analysts approve nothing | `/track/cohort/<id>` |
| Steward | Identity pairs to link or keep apart | `identity.review_queue` minus pairs with a verdict in `identity_reviews` | `/steward/identity` |
| Steward | Schema-drift fixes to approve | `drift_fixes` pending | `/steward/drift` |
| Steward | Failing contract tests | `reports/contract_tests.json`, tests with status fail or error | `/governance/quality` |

Not available: **plan offers above an agent's level awaiting sign-off**. No such store exists: the simulator shows the approver level for a scenario, but nothing saves a plan as waiting for someone else's sign-off. The inbox lists this under "Not shown here" and does not make it up.

Ages: items from the ops store count real days since they were created. Items from the warehouse count days from the data date (28 Sep 2026), which is "today" for the synthetic data.

## Watchlist rules

* **Who may pin what.** A pin uses the same checks as opening the subject (`api/access.py`). Customer and case: `access.golden` and `access.case` (agents only their cases, team leads their team, specialists the hardship rule). Identity: `access.lineage` (stewards, plus the case scope for others). Agent: an agent only themselves, a team lead only agents on their team. Analysts pin only aggregate kinds: cohort, employer, data product. Stewards never pin a customer or case.
* **Ids.** Employer: the radar key (`EMP-xxxxxxxx`). Cohort: `<dimension>:<value>`, the Track pages' format (`month`, `week`, `province`, `fsa`, `strategy`, `product`) plus `bucket` and `team`, each value checked against a pattern and bound as a parameter. Data product: `<schema>.<table>` in gold, silver, identity or features.
* **Small groups.** An employer or cohort under 10 customers shows "numbers hidden" instead of figures.
* **Audit.** Pins and unpins go through `governance.audit.record` (event types `watch_pin`, `watch_unpin`). Marking as seen is not audited (it changes nothing but your own baseline).
* **What changed.** At each look the facts about the subject are saved with the pin (`watchlist.seen_state_json`). The list compares the facts now with those: new contacts, promises kept, broken or made, hardship flag changes (from `hardship_flag_events`), new NBA decisions and overrides, days past due, case status, late payroll and new EI at an employer, rows, new drift fixes and failing tests for a data product, source keys and reviewed pairs for an identity. Read-only: nothing in the warehouse is written.
* **Lost access.** If you can no longer open a pinned subject (a case was reassigned), it stays on the list marked unavailable with the reason, and no facts are read.

## Store

`watchlist` in `common/ops_schema.sql` (`CREATE TABLE IF NOT EXISTS`, unique per user, kind and subject). An older `ops.db` gets the table on first use.

## Frontend

* Nav: an **Inbox** item with a red count badge (read out as "N waiting"), refreshed every minute.
* `/inbox`: groups as cards with a jump list, items with the link, the reason and the age; overdue is said in words and with an icon, not only in colour. One column on a phone, two on wide screens.
* Signed-in home: the 3 most urgent inbox items and the watchlist with what changed. Opening a watched item marks it as seen. Links go to `/track/<kind>/<id>` when the Track pages are present, else to the existing screen.
* `WatchButton({kind, id, label})`: a toggle with `aria-pressed`, updated at once and rolled back with a message if the server refuses.
