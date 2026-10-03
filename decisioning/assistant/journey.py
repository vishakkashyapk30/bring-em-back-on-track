# ruff: noqa: E501
"""The guided demo: one customer's decision journey, told stage by stage for each persona. The sample customer is
chosen from the live data (cached 10 minutes) so that the agent AG-6274 and the team lead of CGY-MID-2 may both open
them; the hardship specialist and the steward use the same customer. Every stage's evidence comes from calling the real
tool as that persona, so the numbers are live and the same row-level access applies."""

from __future__ import annotations

import concurrent.futures as cf
import contextvars
from typing import Any

from api.personas import DEMO_USERS
from decisioning.assistant import data
from decisioning.assistant.tools import ToolContext, run_tool

DEMO_AGENT = DEMO_USERS["agent"]
DEMO_LEAD = DEMO_USERS["team_lead"]
PREFERRED = {"plan_offer": 2, "specialist_referral": 1}


def sample_customer() -> dict | None:
    """Deterministic pick: the demo agent's own scheduled hardship case with a plan offer or referral, a recorded call and
    a scored open promise (also on the demo team lead's team). Falls back to the best case of the demo team's queue."""
    return data.ttl_cached(("sample",), 600, _pick)


def _pick() -> dict | None:
    import pandas as pd

    from api.services.c360 import _q
    from common.config import get_settings

    df = data.queue_df()
    if df is None:
        return None
    sc = get_settings().features_dir / "ptp_scores.parquet"
    scored = set(pd.read_parquet(sc, columns=["case_id"]).case_id) if sc.exists() else set()
    calls = {r["case_id"] for r in _q("SELECT DISTINCT case_id FROM silver.call_transcripts")}
    team = df[(df.assigned_team == DEMO_LEAD.team_id) & (df.status == "scheduled") & (df.treatment != "no_contact")].copy()
    team["mine"] = (team.assigned_agent_id == DEMO_AGENT.user_id).astype(int)
    team["pref"] = team.treatment.map(PREFERRED).fillna(0).astype(int)
    team["hard"] = (team.hardship_flag != "none").astype(int)
    team["poss"] = (team.hardship_flag == "possible").astype(int)
    team["call"] = team.case_id.isin(calls).astype(int)
    team["ptp"] = team.case_id.isin(scored).astype(int)
    team["all4"] = ((team.pref > 0) & (team.hard > 0) & (team.call > 0) & (team.ptp > 0)).astype(int)
    best = team.sort_values(["mine", "all4", "pref", "poss", "hard", "call", "ptp", "priority", "case_id"],
                            ascending=[False, False, False, False, False, False, False, False, True]).head(1)
    if best.empty:
        return None
    r = best.iloc[0]
    return {"case_id": r.case_id, "golden_id": r.golden_id, "name": r["name"], "assigned_agent_id": r.assigned_agent_id,
            "all_criteria": bool(r.all4), "treatment": r.treatment}


def _ctx(persona: str, c: dict | None) -> ToolContext:
    return ToolContext(session=DEMO_USERS[persona], case_id=c["case_id"] if c else None,
                       golden_id=c["golden_id"] if c else None, mode="rules", audit_scores=False)


Q_ROLL = "Of accounts that were 1-30 days past due at the end of March 2026, what share had rolled to a worse bucket by the end of June 2026, by product?"
Q_METRIC = "What is the hardship rate of cases opened in 2026, by primary product?"
Q_REFUSED = "Rank customers by citizenship status so newcomers are called first."


def _stage(id_: str, title: str, narrative: str, screen: str, why: str, tool: str | None = None, args: dict | None = None,
           human: str | None = None) -> dict:
    return {"id": id_, "title": title, "narrative": narrative, "screen": screen, "tool": tool, "tool_args": args,
            "why_it_matters": why, "human_step": human}


def _stages(persona: str, c: dict | None) -> tuple[str, str, list[dict]]:
    g = c["golden_id"] if c else ""
    cid = c["case_id"] if c else ""
    cust = f"/customers/{g}"
    if persona == "agent":
        return ("An agent's day with one customer", "Follow one customer from the queue to an approved action. The assistant proposes; you decide.", [
            _stage("queue", "Today's queue", "Your own cases, highest priority first, with the reason for each.", "/queue",
                   "The work is ranked and explained, so nobody has to guess whom to call first.", "queue_summary"),
            _stage("customer", "Customer 360 and identity", "One view across cards, loans and deposits, with how the records were matched.", cust,
                   "Acting on the wrong person is the costliest mistake; the match confidence is shown.", "customer_360"),
            _stage("nba", "Next best action and the policy gate", "The contact rules run first; the model only ranks what they allow.", cust,
                   "Pressure actions are removed for hardship customers before any model runs.", "nba_proposal"),
            _stage("eligibility", "Program eligibility", "Each hardship program checked rule by rule.", cust,
                   "Rules decide who may be offered what, never a model.", "eligibility_check"),
            _stage("promise", "Promise check against payday", "Break risk of the open promise and a what-if for the payday date.", cust,
                   "A promise due before payday is likelier to break; a later date may be safer (model estimate, not cause and effect).", "promise_check"),
            _stage("notes", "Call summary", "Notes drafted from the recorded call, checked against the promise on record.", f"/customers/{g}",
                   "Typing notes costs minutes per call; only approved notes are saved.", "call_summary",
                   human="Open the call notes, edit if needed and approve."),
            _stage("decision", "Approve, edit or override", "You approve the proposed action, change it to another allowed one, or override with a reason.", cust,
                   "Every decision is audited; an override needs a reason code.", None,
                   human="Approve, edit or override the proposed action on the customer page."),
        ])
    if persona == "hardship_specialist":
        return ("A hardship specialist's review of one customer", "From the review board to a confirmed or lowered flag. Only you can change the flag.", [
            _stage("board", "Review board", "Customers flagged possible who wait for a person; overdue first.", "/hardship/board",
                   "Hardship reviews have a deadline; the board shows who is late.", "hardship_board"),
            _stage("missed", "Missed offers", "Flagged customers never offered a program although one fits.", "/hardship/missed",
                   "Customers in difficulty should not miss help because nobody offered it.", "missed_offers"),
            _stage("customer", "The customer", "Flags, holdings and identity for the sample customer.", cust,
                   "You see the whole customer before deciding.", "customer_360"),
            _stage("eligibility", "Eligibility rules", "Every program checked rule by rule with the approver level.", cust,
                   "The rules, not a model, decide what can be offered.", "eligibility_check"),
            _stage("simulator", "Plan simulator", "New payment, months to clear, interest and share of surplus. Saves nothing.", f"/hardship/simulator/{cid}",
                   "Shows whether the plan is affordable before it is offered.", "simulator"),
            _stage("approver", "Approver level", "Whether the plan is within agent limits or needs a higher approver.", f"/hardship/simulator/{cid}",
                   "Plans beyond limits must go to the right approver.", "simulator"),
            _stage("decide", "Confirm or lower the flag, with a reason", "Confirm hardship (link a program) or lower the flag with a written reason.", "/hardship/board",
                   "The flag is a latch: models and rules can raise it, only a person can lower it, with a reason on the audit log.", None,
                   human="Confirm or lower the flag on the board and write the reason."),
        ])
    if persona == "team_lead":
        return ("A team lead's morning", "Approve routine batches after a sample check, and know what happens if a channel fails.", [
            _stage("queue", "Team queue", "What the team has to work today.", "/queue", "One picture of the day's workload.", "queue_summary"),
            _stage("batch", "Batch queue and the 2% sample", "Routine reminders wait for you; check a 2% sample first.", "/queue?view=batch",
                   "A sample check keeps volume approval safe without reading every case.", "batch_queue"),
            _stage("stress", "Stress test: dialer down", "Re-runs the allocator without calls and shows which actions slip; the same test works for SMS (ask the assistant).", "/team",
                   "Plan cover before the outage, not after.", "stress_test", {"channel": "call"}),
            _stage("guardrails", "Override rate and guardrails", "Overrides, and pressure on hardship customers, which must be zero.", "/team",
                   "Guardrails you can see are guardrails you can defend.", "guardrails"),
            _stage("agents", "Team load", "Who is near capacity.", "/team", "Capacity decides what slips first.", "team_agents"),
            _stage("spot", "Spot-check one case", "Open one case from your team to see the proposed action and the rules behind it.", cust,
                   "A spot check shows whether the proposals make sense before you approve in bulk.", "nba_proposal"),
            _stage("approve", "Approve the batch", "Approve after checking the sample.", "/queue?view=batch",
                   "Approval is a person's decision and is audited.", None, human="Open the batch, check the sample and approve."),
        ])
    if persona == "analyst":
        return ("An analyst's questions", "Certified numbers with the SQL shown, honest about causality, and firm refusals.", [
            _stage("metric", "A certified metric question", "Answered from the semantic layer; the SQL is shown.", "/ask",
                   "Everyone gets the same definition of a metric.", "metric_question", {"question": Q_METRIC}),
            _stage("roll", "Roll rate", "Share of early-stage accounts that rolled to a worse bucket between quarter-ends.", "/ask",
                   "Roll rate is the early-warning number for losses.", "metric_question", {"question": Q_ROLL}),
            _stage("map", "Map", "Broken-promise rate by postal area; small areas hidden.", "/map",
                   "Shows where outreach struggles, without exposing individuals.", "geo_map"),
            _stage("scorecard", "Scorecard, honest about causality", "Randomised cells are causal; the rest is observed.", "/team",
                   "Prevents a wrong conclusion from observational data.", "scorecard"),
            _stage("refused", "A refused question", "Ranking customers by citizenship is refused, always.", "/ask",
                   "Protected attributes never drive a decision, list or ranking.", "guardrail_check", {"question": Q_REFUSED}),
            _stage("model", "Model card", "The promise-break model against the bank's v2.1 on the same promises.", "/governance/monitoring",
                   "A new model must beat the old one on the same data.", "model_card"),
            _stage("fairness", "Fairness", "Proxy and outcome tests, aggregates only.", "/governance/fairness",
                   "Proves the model does not lean on protected attributes.", "fairness_report"),
        ])
    return ("A data steward's checks", "Identity, data quality, contracts and the audit trail.", [
        _stage("identity", "Identity review queue", "Grey-band matches wait for a person; names are masked.", "/steward/identity",
               "Wrong merges are costly, so uncertain ones go to a person.", "identity_queue"),
        _stage("lineage", "Match confidence and lineage", "Every source key behind one golden customer.", cust, "Every number can be traced to its source.", "identity_lineage",
               {"golden_id": g} if g else None),
        _stage("quality", "Data quality report", "Issues found and how each is handled.", "/governance/quality", "Known issues are documented, not hidden.", "data_quality"),
        _stage("contracts", "Contract tests", "From the last build.", "/governance/contract", "A failed contract blocks publishing.", "contract_tests"),
        _stage("parity", "Feature parity", "Training and serving features must agree.", "/governance/monitoring", "Prevents silent model drift from skew.", "feature_parity"),
        _stage("monitoring", "Freshness", "Against the 26-hour contract.", "/governance/monitoring", "Stale data carries a warning.", "monitoring"),
        _stage("audit", "Audit log", "Append-only record of every write and assistant run.", "/governance/audit", "Accountability for every customer-affecting step.", "audit_log"),
    ])


def _run_stage(persona: str, st: dict, c: dict | None) -> dict:
    if not st["tool"]:
        return {**st, "evidence": {}, "status": "needs_approval", "summary": st["human_step"], "ms": 0}
    ctx = _ctx(persona, c)
    args = dict(st["tool_args"] or {})
    if st["tool"] == "identity_lineage" and not args.get("golden_id"):
        args = {}
    if args.pop("golden_id", None):
        ctx.golden_id = c["golden_id"] if c else None
    r = run_tool(st["tool"], ctx, args)
    return {**st, "evidence": r["evidence"], "status": r["status"], "summary": r["summary"], "ms": r["ms"]}


def journey(persona: str) -> dict:
    """The guided demo for one persona. Stages run in parallel; the whole answer is cached for a minute."""
    return data.ttl_cached(("journey", persona), 60, lambda: _build(persona))


def _build(persona: str) -> dict:
    c = sample_customer() if persona != "analyst" else None
    title, intro, stages = _stages(persona, c)
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        futs = [ex.submit(contextvars.copy_context().run, _run_stage, persona, st, c) for st in stages]
        done: list[dict[str, Any]] = [f.result() for f in futs]
    return {"persona": persona, "title": title, "intro": intro,
            "customer": {"golden_id": c["golden_id"], "case_id": c["case_id"], "name": c["name"]} if c else None,
            "stages": done}


def prewarm() -> None:
    """Fill the slow caches in the background (the sample customer and the stress test) so the first demo is quick."""
    import threading

    def go() -> None:
        try:
            from common.config import get_settings

            if get_settings().warehouse_path.exists():
                sample_customer()
                run_tool("stress_test", _ctx("team_lead", None), {"channel": "call"})
        except Exception:  # noqa: BLE001 - warming is best effort
            pass

    threading.Thread(target=go, daemon=True).start()
