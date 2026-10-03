# The persona assistant

An assistant for each of the five personas. It plans steps, calls the same production functions as the screens, shows every step with its evidence, and proposes actions that a person approves in the existing screens. It never writes customer data and never contacts anyone. Every run is written to the audit log (event type `assistant_run`, with the steps in the details).

## Endpoints

| Endpoint | Purpose |
|---|---|
| `POST /api/assistant/run` | Body `{goal?, case_id?, golden_id?, mode?}` where mode is `rules` or `llm`. Returns the plan, the steps with evidence, findings, proposals, a summary, `mode_used`, `mode_note` and `audit_id`. |
| `GET /api/assistant/suggestions` | The briefing and five or six goals for the signed-in persona. Every one is run to completion by `tests/unit/test_assistant.py`. |
| `GET /api/demo/journey/{persona}` | The guided demo for your own persona: one customer's journey in 6 to 8 stages, each with live evidence from the real tool. |

## What each persona can do

| Persona | Tools | Briefing |
|---|---|---|
| Agent | queue_summary, customer_360, identity_lineage, nba_proposal, eligibility_check, promise_check, call_summary, policy_answer | Queue, top case, proposed action, promise against payday, call notes |
| Hardship specialist | hardship_board, missed_offers, override_report, customer_360, nba_proposal, eligibility_check, simulator, call_summary, promise_check, policy_answer, queue_summary | Board, missed offers, eligibility, simulation, rule overrides |
| Team lead | queue_summary, batch_queue, stress_test, guardrails, team_agents, scorecard, override_report, audit_log, metric_question, policy_answer, geo_map | Queue, batches, dialer stress test, guardrails, team load |
| Analyst | metric_question, scorecard, geo_map, model_card, fairness_report, data_quality, stress_test, policy_answer | Certified metric, scorecard, map, model card, fairness |
| Data steward | identity_queue, identity_lineage, customer_360, data_quality, contract_tests, feature_parity, monitoring, audit_log, model_card, fairness_report | Identity queue, lineage, quality, contract tests, parity, audit |

`guardrail_check` is open to everyone: it shows why a request is refused.

## Safety rules

1. Authorisation comes first and is the same in rules mode and language-model mode. A tool the role may not use gives a failed step with a reason and no data. Row-level access (`api/access.py`) is checked before any case, customer or call is read: an agent sees own cases, a team lead the team's, analysts aggregates only.
2. The policy gate and the hardship latch stay in force because the assistant reuses `decisioning` and never bypasses it. Proposals carry the role that must approve and a link to the existing screen.
3. Protected attributes are not used anywhere. Requests that ask for them (or for proxies, personal details or actions) are refused by the guardrails before any plan or model runs.
4. Questions go through `nlq.pipeline.ask` inside the persona's Ask scope.
5. The what-if and the simulator save nothing. Estimates are labelled "model estimate, not cause and effect".

## Rules mode and language-model mode

- Rules: the goal text is matched with keywords to one plan from a closed list (`decisioning/assistant/plans.py`). No goal means the briefing. A request that is not recognised gets the briefing with a note. The summary is a template over the findings.
- Language model: the model is shown only the plans and tools the role may use. It picks a plan id and fills slots (case, customer, date, amount, channel, question), then words the summary from the step evidence. The output is checked against `llm/schemas/assistant_plan.json`. A plan outside the role's list, a named tool the role may not use, or a slot whose value is not in the goal text is dropped. A case slot is re-checked with `api/access`. A summary is accepted only if every number in it appears in the evidence. On any problem the rules plan or template runs, and `mode_note` says why. The tools and the plan steps always come from code.
- `mode_used` is `rules` or `language model`. If `llm` is asked for and no model is available, rules run and `mode_note` explains. The prompt is `llm/prompts/assistant_plan/v1.md` and has an offline handler, so `LLM_PROVIDER=offline` always works.

## Guided demo

The sample customer is chosen from the live data and cached for 10 minutes: the demo agent's own scheduled case with a plan offer or specialist referral, hardship flagged, a recorded call and a scored promise, on the demo team lead's team. The hardship specialist and the steward use the same customer. The analyst has no customer: aggregates only.

## How to extend

1. Add a tool in `decisioning/assistant/tools.py` with `@tool(name, description, roles)`. Call the production function the matching endpoint uses, call `_case(ctx)` or `_golden(ctx)` first when it touches a customer, and return a `ToolResult` with a summary, evidence, findings and proposals.
2. Add a `Plan` to `PLANS` in `plans.py` with the keyword patterns, a label and a goal. Tests check that the goal picks its own plan and runs to completion.
3. Add a journey stage in `journey.py` with a screen, a narrative and why it matters.
