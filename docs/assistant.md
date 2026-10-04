# The persona assistant

An assistant for each of the five personas. It plans steps, calls the same production functions as the screens, shows every step with its evidence, and proposes actions that a person approves in the existing screens. It never writes customer data and never contacts anyone. Every run is written to the audit log (event type `assistant_run`, with the steps in the details).

## Endpoints

| Endpoint | Purpose |
|---|---|
| `POST /api/assistant/run` | Body `{goal?, case_id?, golden_id?, mode?}` where mode is `rules` or `llm`. Returns the plan, the steps with evidence, findings, proposals, a summary, `mode_used`, `mode_note` and `audit_id`. |
| `GET /api/assistant/suggestions` | The briefing and five to ten goals for the signed-in persona. Every one is run to completion by `tests/unit/test_assistant.py`. |
| `GET /api/demo/journey/{persona}` | The guided demo for your own persona: one customer's journey in 6 to 8 stages, each with live evidence from the real tool. |

## What each persona can do

| Persona | Tools | Briefing |
|---|---|---|
| Agent | queue_summary, customer_360, identity_lineage, nba_proposal, eligibility_check, promise_check, call_summary, policy_answer | Queue, top case, proposed action, promise against payday, call notes |
| Hardship specialist | hardship_board, missed_offers, override_report, outage_victims, customer_360, nba_proposal, eligibility_check, simulator, call_summary, promise_check, policy_answer, queue_summary | Board, missed offers, eligibility, simulation, rule overrides |
| Team lead | queue_summary, batch_queue, stress_test, guardrails, team_agents, scorecard, override_report, audit_log, metric_question, policy_answer, geo_map, employer_radar, playbook_proposals, outage_victims, call_friction | Queue, batches, dialer stress test, guardrails, team load |
| Analyst | metric_question, scorecard, geo_map, model_card, fairness_report, data_quality, stress_test, employer_radar, data_drift, call_friction, policy_answer | Certified metric, scorecard, map, model card, fairness |
| Data steward | identity_queue, identity_lineage, customer_360, data_quality, contract_tests, feature_parity, monitoring, audit_log, model_card, fairness_report, data_drift | Identity queue, lineage, quality, contract tests, parity, audit |

`guardrail_check` is open to everyone: it shows why a request is refused.

`ask_data` (every role, inside its Ask scope) and `search_interactions` (agent, hardship specialist, team lead; notes, call transcripts and voice transcripts of cases the person may read) are mostly used by the agent in language-model mode.

### Team and data tools (read only)

Five tools (`decisioning/assistant/tools_ops.py`) make the radar, playbook, outage, drift and friction modules reachable. `stress_test` (S6, `decisioning/stress_test.py`) was already a tool. Each tool allows the same roles as the screen or route that shows the same data. None writes: no proposal is stored, no fix is recorded, nothing is sent. An action is a proposal that links to the screen where a person approves it.

| Tool | Roles | What it reads | Approval screen |
|---|---|---|---|
| `employer_radar` (S1) | team lead, analyst | Weekly late-payroll and new-EI clusters per employer; employers under 10 customers are hidden; no customer lists | Team page (team lead) |
| `playbook_proposals` | team lead | Stored playbook proposals (radar, outage shield, regional): counts, titles, status | `/team` Playbooks tab |
| `outage_victims` (H5) | hardship specialist, team lead | Candidate list for the payment outage, proposed fee reversals and holds; customer IDs only for cases the person may see | `/team` (team lead), `/hardship/board` |
| `data_drift` (S3) | steward, analyst | Tables that changed shape after a release and the drafted fixes (read only) | `/steward/drift` (steward only) |
| `stress_test` (S6) | team lead, analyst | Allocator re-run with a channel down or agents absent | `/team` |
| `call_friction` (A3) | analyst, team lead | Overtalk, holds and long silence by delinquency stage; stages under 10 calls hidden; call-level measures only, no speaker traits, no agent or customer ranking | none (descriptive; must pass the proxy test before any use in a decision) |

An analyst never gets an individual customer row from these tools. Citations follow the existing shapes: `data` (the data product read), `sql` (the friction and radar queries are shown as "SQL used").

## Safety rules

1. Authorisation comes first and is the same in rules mode and language-model mode. A tool the role may not use gives a failed step with a reason and no data. Row-level access (`api/access.py`) is checked before any case, customer or call is read: an agent sees own cases, a team lead the team's, analysts aggregates only.
2. The policy gate and the hardship latch stay in force because the assistant reuses `decisioning` and never bypasses it. Proposals carry the role that must approve and a link to the existing screen.
3. Protected attributes are not used anywhere. Requests that ask for them (or for proxies, personal details or actions) are refused by the guardrails before any plan or model runs.
4. Questions go through `nlq.pipeline.ask` inside the persona's Ask scope.
5. The what-if and the simulator save nothing. Estimates are labelled "model estimate, not cause and effect".

## Rules mode and language-model mode

- Rules: the goal text is matched with keywords to one plan from a closed list (`decisioning/assistant/plans.py`). No goal means the briefing. A request that is not recognised gets the briefing with a note. Persona plans now include employer radar and playbooks and outage victims (team lead), employer radar with a stress test, schema drift and call friction (analyst), schema drift (steward) and outage victims (hardship specialist). The summary is a template over the findings.
- Language model: the assistant is an agent. The model is shown only the tools the role may use, chooses which to call and in what order, reads each result and writes an answer that must cite the steps and use only numbers and ids from their evidence. Every call goes through the same role, row-level and Ask-scope checks as rules mode. Limits: 6 tool calls, 8 turns, 45 s. On any problem the rules run and `mode_note` says why. Details, the `citations` Sources block and the evaluation: `docs/assistant_agent.md`.
- `mode_used` is `rules` or `language model`. If `llm` is asked for and no model is available, rules run and `mode_note` explains. The prompts (`llm/prompts/assistant_agent/v1.md`, and `assistant_plan/v1.md` for the briefing summary) have offline handlers, so `LLM_PROVIDER=offline` always works.

## Guided demo

The sample customer is chosen from the live data and cached for 10 minutes: the demo agent's own scheduled case with a plan offer or specialist referral, hardship flagged, a recorded call and a scored promise, on the demo team lead's team. The hardship specialist and the steward use the same customer. The analyst has no customer: aggregates only.

## How to extend

1. Add a tool in `decisioning/assistant/tools.py` (or `tools_ops.py` for the team and data tools) with `@tool(name, description, roles)`. Call the production function the matching endpoint uses, call `_case(ctx)` or `_golden(ctx)` first when it touches a customer, and return a `ToolResult` with a summary, evidence, findings and proposals.
2. Add a `Plan` to `PLANS` in `plans.py` with the keyword patterns, a label and a goal. Tests check that the goal picks its own plan and runs to completion.
3. Add a journey stage in `journey.py` with a screen, a narrative and why it matters.
