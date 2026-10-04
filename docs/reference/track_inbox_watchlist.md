# Track: follow one subject over time

Each persona picks ONE real subject from the warehouse, follows its full history, reads insights (each with a plain-English reason and its source) and takes actions. Every action uses an existing endpoint that already writes `governance/audit.record`. The policy gate and the hardship latch rules are untouched: the latch is lowered only by a person with a reason, through `POST /hardship/{golden_id}/flag`.

Open it from the **Track** nav item (`/track`), or from `/demo` with **Track one over time** on any persona (it signs in and opens the suggested subject).

## What each persona tracks and can do

| Persona | Subject (picker scope) | What they see | Actions (existing endpoints) |
|---|---|---|---|
| Agent | One of their own customers: a case with `assigned_agent_id` = the agent (searchable by name, golden ID or case ID) | One chronological timeline across accounts, cases, promises (made, kept, broken), contacts, agent notes, calls with transcripts, recordings (link to the call page player), hardship flag events, NBA decisions and overrides, approved post-call summaries; tabs for promises, calls and accounts; a "what changed" strip | Current NBA card with approve, change, override (`POST /nba/{case_id}/decision`); links to review and approve post-call summaries (`/calls/{contact_id}`, which posts `/calls/{contact_id}/summary/approve`); link to the full customer page |
| Hardship specialist | A customer open under the row rule (board, flagged hardship or vulnerable, assigned to them or their team, or flagged in the ops store) | Hardship journey: signals from contacts, transcripts and notes (recordings play inline, call-level measures only), flag events, offers made and declined, eligibility per program (rules only), plan survival, simulated plans | Confirm hardship and link a program, lower the flag with a required reason (both `POST /hardship/{golden_id}/flag`), open the simulator (`/hardship/simulator/{case_id}`) |
| Team lead | An agent on their team, or an employer from the radar (10 or more customers) | Agent: promise kept rate by month, contacts and right-party contacts by month, calls outside permitted hours, overrides and reasons (bank record and this app), guardrail counts, case load and today's queue. Employer: customers, open cases and exposure (aggregates), no-payroll share by month, new EI deposits by week, cases opened by month; points under 10 hidden | Approve the team's pending batches (`POST /batches/{id}/approve`), approve playbook proposals (`POST /playbooks/{id}/approve`), links to the queue and the agent roster (reassignment happens in the case system; there is no reassign endpoint) |
| Analyst | A cohort: `month:YYYY-MM`, `week:YYYY-MM-DD` (a Monday), `province:XX`, `fsa:A1A`, `strategy:CODE`, `product:NAME` | Cure and roll curves by days since opening, 30-day cure rate by month opened, promise kept rate by month due, cure rate by certified breakdowns (drivers). Aggregates only; cohorts and groups under 10 are hidden | Propose a strategy test (`POST /track/cohort/{id}/propose`): stored as a pending proposal in the playbook store and audited; read-only to the analyst, approved by a team lead with `POST /playbooks/{id}/approve` |
| Steward | A golden customer's identity, or a data product (any dbt model) | Identity: source keys and match confidence per source system, CRM merges, grey-band pairs and verdicts, contract tests on `gold.c360_customer`, quality issues and drift events on its source tables. Product: lineage (dbt parents and children), contract test results, quality issues, incidents and schema changes, match confidence per system for `gold.c360_customer`. Never calls, notes or summaries | Decide grey-band pairs (`POST /steward/identity/{pair_id}`), approve drafted drift fixes (`POST /drift/{fix_id}/approve`) |

## Endpoints

All under `/api`, in `api/routers/track.py` (schemas in `api/schemas/track.py`, logic in `api/services/track.py`).

| Method and path | Roles | Purpose |
|---|---|---|
| `GET /track/kinds` | all five | Subject types for the role and the guided demo's suggested subject |
| `GET /track/subjects?kind=&q=` | per kind | Picker list, scoped to the person |
| `GET /track/{kind}/{id}` | per kind | The tracker: header, insights, sections (timeline, series, tables, facts) and actions |
| `POST /track/cohort/{id}/propose` | analyst | Propose a strategy test (audited, contacts nobody) |

## Rules it keeps

* **Authorisation first.** `track.authorize` runs before any of the subject's data is read: the role decides the kinds (agent and specialist: customer; team lead: agent, employer; analyst: cohort; steward: identity, product). Customers use `api/access.golden` (agent: own cases; specialist: the hardship row rule in `docs/reference/row_scope.md`), identities use `access.lineage`, agents must be on the lead's team, employers need 10 or more customers, cohort ids are matched against patterns and allowlists before any value reaches SQL.
* **Aggregates only for analysts.** Cohort views carry no golden ID, case ID or name; cohorts under 10 customers are refused, and series points and driver groups under 10 are hidden. Employer views follow the same rule.
* **Read-only warehouse.** One read-only DuckDB connection per view. The only write is the analyst proposal, through `decisioning.playbooks.store` plus `governance.audit.record`. Approving a strategy-test proposal records the approval and creates no batch.
* **Every insight has a reason and a source.** The source is the SQL that produced it (shown in full), or the record ids and table behind it, or the report file. Cohort SQL is built from the certified semantic metrics (`cure_rate`, `promise_kept_rate`) and dimensions in `semantic/registry.py`.
* **Causal honesty.** Cohort comparisons are labelled observed, not causal; strategy codes are compared within a stage on the scorecard, not ranked here.
* **No protected attributes.** None are read; recordings show call-level measures only.

## Frontend

`/track` (picker) and `/track/:kind/:id` (tracker) in `web/src/pages/track/`; hooks in `web/src/api/track.ts`. The tracker is one header card, an insight strip (three at first, more on request) and tabs, so each view fits on a screen. Charts follow the app's chart style (brand red, ink, teal; recessive grid; a table view under every chart; dashed strokes as a second cue). Backgrounds are white or cream only. Each tracker header carries the watchlist `WatchButton`.

## Tests

`tests/unit/test_track.py` (role by kind refusals before any warehouse read, an agent refused another agent's customer, specialist row rule, steward lineage only, team scope, employer suppression, cohort id validation, analyst views free of individual ids with suppression, the audited proposal and its batch-free approval, router refusals) and `web/src/pages/track/Track.test.tsx` (the picker lists what the API returns and switches kind, an empty scope, a refused subject shows the reason).

## Inbox and watchlist

Two features that help each person keep track of their work. They add no new approval logic.

* **Waiting for you** (`/inbox`): one list per persona of every pending human review in the system. Each item says what it is, why it needs you (in plain English), how long it has waited or when it is due, and links to the existing screen where you act on it. The inbox only reads.
* **Saved watchlist**: pin a customer, case, agent, employer, cohort, data product or identity to follow it. The signed-in home shows what changed since you last looked.

### Endpoints

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

### What each persona sees in the inbox

Every source reads the same store as the screen it links to, with the same row scope (`docs/reference/row_scope.md`).

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

### Watchlist rules

* **Who may pin what.** A pin uses the same checks as opening the subject (`api/access.py`). Customer and case: `access.golden` and `access.case` (agents only their cases, team leads their team, specialists the hardship rule). Identity: `access.lineage` (stewards, plus the case scope for others). Agent: an agent only themselves, a team lead only agents on their team. Analysts pin only aggregate kinds: cohort, employer, data product. Stewards never pin a customer or case.
* **Ids.** Employer: the radar key (`EMP-xxxxxxxx`). Cohort: `<dimension>:<value>`, the Track pages' format (`month`, `week`, `province`, `fsa`, `strategy`, `product`) plus `bucket` and `team`, each value checked against a pattern and bound as a parameter. Data product: `<schema>.<table>` in gold, silver, identity or features.
* **Small groups.** An employer or cohort under 10 customers shows "numbers hidden" instead of figures.
* **Audit.** Pins and unpins go through `governance.audit.record` (event types `watch_pin`, `watch_unpin`). Marking as seen is not audited (it changes nothing but your own baseline).
* **What changed.** At each look the facts about the subject are saved with the pin (`watchlist.seen_state_json`). The list compares the facts now with those: new contacts, promises kept, broken or made, hardship flag changes (from `hardship_flag_events`), new NBA decisions and overrides, days past due, case status, late payroll and new EI at an employer, rows, new drift fixes and failing tests for a data product, source keys and reviewed pairs for an identity. Read-only: nothing in the warehouse is written.
* **Lost access.** If you can no longer open a pinned subject (a case was reassigned), it stays on the list marked unavailable with the reason, and no facts are read.

### Store

`watchlist` in `common/ops_schema.sql` (`CREATE TABLE IF NOT EXISTS`, unique per user, kind and subject). An older `ops.db` gets the table on first use.

### Frontend

* Nav: an **Inbox** item with a red count badge (read out as "N waiting"), refreshed every minute.
* `/inbox`: groups as cards with a jump list, items with the link, the reason and the age; overdue is said in words and with an icon, not only in colour. One column on a phone, two on wide screens.
* Signed-in home: the 3 most urgent inbox items and the watchlist with what changed. Opening a watched item marks it as seen. Links go to `/track/<kind>/<id>` when the Track pages are present, else to the existing screen.
* `WatchButton({kind, id, label})`: a toggle with `aria-pressed`, updated at once and rolled back with a message if the server refuses.
