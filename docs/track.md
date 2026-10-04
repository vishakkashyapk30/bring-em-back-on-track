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

* **Authorisation first.** `track.authorize` runs before any of the subject's data is read: the role decides the kinds (agent and specialist: customer; team lead: agent, employer; analyst: cohort; steward: identity, product). Customers use `api/access.golden` (agent: own cases; specialist: the hardship row rule in `docs/row_scope.md`), identities use `access.lineage`, agents must be on the lead's team, employers need 10 or more customers, cohort ids are matched against patterns and allowlists before any value reaches SQL.
* **Aggregates only for analysts.** Cohort views carry no golden ID, case ID or name; cohorts under 10 customers are refused, and series points and driver groups under 10 are hidden. Employer views follow the same rule.
* **Read-only warehouse.** One read-only DuckDB connection per view. The only write is the analyst proposal, through `decisioning.playbooks.store` plus `governance.audit.record`. Approving a strategy-test proposal records the approval and creates no batch.
* **Every insight has a reason and a source.** The source is the SQL that produced it (shown in full), or the record ids and table behind it, or the report file. Cohort SQL is built from the certified semantic metrics (`cure_rate`, `promise_kept_rate`) and dimensions in `semantic/registry.py`.
* **Causal honesty.** Cohort comparisons are labelled observed, not causal; strategy codes are compared within a stage on the scorecard, not ranked here.
* **No protected attributes.** None are read; recordings show call-level measures only.

## Frontend

`/track` (picker) and `/track/:kind/:id` (tracker) in `web/src/pages/track/`; hooks in `web/src/api/track.ts`. The tracker is one header card, an insight strip (three at first, more on request) and tabs, so each view fits on a screen. Charts follow the app's chart style (brand red, ink, teal; recessive grid; a table view under every chart; dashed strokes as a second cue). Backgrounds are white or cream only. Each tracker header carries the watchlist `WatchButton`.

## Tests

`tests/unit/test_track.py` (role by kind refusals before any warehouse read, an agent refused another agent's customer, specialist row rule, steward lineage only, team scope, employer suppression, cohort id validation, analyst views free of individual ids with suppression, the audited proposal and its batch-free approval, router refusals) and `web/src/pages/track/Track.test.tsx` (the picker lists what the API returns and switches kind, an empty scope, a refused subject shows the reason).
