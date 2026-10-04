# ruff: noqa: E501
"""The agentic assistant (decisioning/assistant/llm_agent.py) with scripted fake models: the loop, authorisation of every
call, argument and id checks, budgets, fallbacks, grounding of the answer, citations, audit and the HTTP layer. No
network: every model here is a Python function, and the provider is forced offline by tests/conftest.py."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.deps import COOKIE, sign
from api.personas import DEMO_USERS
from common.protected import PROTECTED_ATTRIBUTES
from decisioning.assistant import llm_agent as A
from decisioning.assistant import runner
from decisioning.assistant.tools import TOOLS, Tool, ToolResult, kv, proposal, table

ROOT = Path(__file__).resolve().parents[2]
PERSONAS = list(DEMO_USERS)
needs_warehouse = pytest.mark.skipif(not (ROOT / "data" / "warehouse.duckdb").exists(), reason="no warehouse built")


# ---------------------------------------------------------------- helpers: fake tools and scripted models

def _fake_tool(name="fake_count", roles=("steward", "agent"), n=1326, case="CS-2026-000777", calls=None):
    def fn(ctx, **kw):
        if calls is not None:
            calls.append((name, kw, ctx.case_id))
        r = ToolResult(f"{n:,} records checked; worst case {case} at 0.42.",
                       {**table(["Case", "Customer", "Score"], [[case, "J. Example", 0.42]]), "kv": kv([("Records", n)]),
                        "cites": [{"doc_id": "POL-7", "section": "4.2", "quote": "Do not pressure."}]},
                       cites=[{"doc_id": "POL-7", "section": "4.2"}])
        r.findings.append(f"{n:,} records checked.")
        r.proposals.append(proposal(f"review-{case}", f"Review {case}", "A person approves.", "review", "/queue", "agent"))
        r.proposals.append(proposal("second", "Second proposal", "A person approves.", "review", "/queue", "agent"))
        return r

    return Tool(name, "A fake tool for tests: counts records.", frozenset(roles), fn)


def script(*actions):
    """A scripted model: returns the given actions in order (each a dict or a callable of the inputs)."""
    seen: list[dict] = []
    queue = list(actions)

    def model(inputs):
        seen.append(json.loads(json.dumps(inputs, default=str)))
        a = queue.pop(0) if queue else {"action": "final", "answer": "Done.", "cited_steps": []}
        a = a(inputs) if callable(a) else a
        if isinstance(a, Exception):
            raise a
        base = {"thought": "next", "tool": None, "args": {}, "answer": None, "cited_steps": []}
        return {**base, **a, "_meta": {"provider": "fake"}}

    model.seen = seen
    return model


def call(tool, **args):
    return {"action": "call_tool", "tool": tool, "args": args}


def final(answer, cited=("s1",), **extra):
    return {"action": "final", "answer": answer, "cited_steps": list(cited), **extra}


@pytest.fixture
def fake_tool(monkeypatch):
    calls: list = []
    monkeypatch.setitem(TOOLS, "fake_count", _fake_tool(calls=calls))
    return calls


def _use(monkeypatch, model):
    monkeypatch.setattr(A, "_model", model)
    return model


# ---------------------------------------------------------------- catalogue and schemas

@pytest.mark.parametrize("persona", PERSONAS)
def test_catalogue_lists_only_the_roles_tools(persona):
    cat = A.catalogue(persona)
    assert cat and all(persona in TOOLS[t["name"]].roles for t in cat)
    for t in cat:  # every argument schema is a valid JSON schema
        import jsonschema

        jsonschema.Draft7Validator.check_schema(A.arg_schema(t["name"]))


def test_role_specific_tools():
    assert "hardship_board" not in A.allowed_tools("agent")
    assert "ask_data" in A.allowed_tools("agent")
    assert "search_interactions" not in A.allowed_tools("analyst") and "search_interactions" not in A.allowed_tools("steward")
    if "search_interactions" in TOOLS:
        assert "search_interactions" in A.allowed_tools("agent")


def test_ops_tools_are_in_the_catalogue_for_their_roles_only():
    ops = {"employer_radar", "playbook_proposals", "outage_victims", "data_drift", "call_friction", "stress_test"}
    seen = {p: ops & set(A.allowed_tools(p)) for p in PERSONAS}
    assert seen["team_lead"] == ops - {"data_drift"} and seen["analyst"] == ops - {"playbook_proposals", "outage_victims"}
    assert seen["steward"] == {"data_drift"} and seen["hardship_specialist"] == {"outage_victims"} and seen["agent"] == set()
    cat = {t["name"]: t for t in A.catalogue("team_lead")}
    assert "status" in cat["playbook_proposals"]["args"] and set(A.ARGS["playbook_proposals"]["status"]["enum"]) >= {"pending_approval"}
    for n in ops:
        assert n in A.DATA_SOURCES
    prompt = (ROOT / "llm" / "prompts" / "assistant_agent" / "v1.md").read_text()
    for n in ops:
        assert n in prompt, n


def test_ops_tool_results_give_data_and_sql_citations(monkeypatch):
    def fn(ctx, **kw):
        return ToolResult("2 stages shown.", {**table(["Stage", "Calls"], [["1-30", 12]]), "text": "SQL used:\nSELECT 1 FROM silver.call_transcripts t"})

    monkeypatch.setitem(TOOLS, "call_friction", Tool("call_friction", "x", frozenset({"analyst"}), fn))
    from decisioning.assistant.tools import ToolContext, run_tool

    r = run_tool("call_friction", ToolContext(session=DEMO_USERS["analyst"]))
    step = {"id": "s1", "tool": "call_friction", "title": "t", "status": r["status"], "summary": r["summary"], "evidence": r["evidence"], "cites": r["cites"]}
    kinds = {c["kind"] for c in A.collect_citations([step])}
    assert {"step", "sql", "data"} <= kinds


def test_parse_action():
    ok, err = A.parse_action({"thought": "t", "action": "call_tool", "tool": "x", "args": {"a": None, "b": 1}, "answer": None, "cited_steps": []})
    assert ok and ok["args"] == {"b": 1} and not err
    assert A.parse_action({"action": "dance"})[0] is None
    assert A.parse_action({"thought": "t", "action": "final", "tool": None, "args": {}, "answer": "", "cited_steps": []})[0] is None
    assert A.parse_action("not json")[0] is None
    assert A.parse_action({"thought": "t", "action": "call_tool", "tool": "", "args": {}, "answer": None, "cited_steps": []})[0] is None


# ---------------------------------------------------------------- grounding

def _steps():
    steps = [{"id": "s1-fake_count", "tool": "fake_count", "status": "done"}, {"id": "s2-nope", "tool": "nope", "status": "failed"}]
    results = {"s1-fake_count": {"status": "done", "summary": "1,326 records; worst CS-2026-000777 at 0.42; share 0.305",
                                 "evidence": {"rows": [[1325.6]]}, "findings": [], "proposals": []},
               "s2-nope": {"status": "failed", "summary": "Not allowed", "evidence": {}, "findings": [], "proposals": []}}
    return steps, results


def test_check_answer_accepts_grounded_numbers_and_ids():
    steps, results = _steps()
    for text in ("There are 1326 records [s1].", "1,326 records; CS-2026-000777 is worst at 0.42 [s1].",
                 "About 30.5% share [s1].", "Roughly 31% [s1].", "Balance about 1,326 [s1]."):
        ok, cited, why = A.check_answer(text, ["s1"], steps, results, "goal", [])
        assert ok, (text, why)
        assert cited == ["s1-fake_count"]


def test_check_answer_rejects():
    steps, results = _steps()
    bad = [("There are 9999 records [s1].", ["s1"], "number"),
           ("Case CS-2026-123456 is worst [s1].", ["s1"], "id"),
           ("1,326 records [s9].", ["s1"], "does not exist"),
           ("1,326 records.", ["s7-x"], "does not exist"),
           ("1,326 records.", [], "did not cite"),
           ("1,326 records.", ["s2-nope"], "did not cite"),
           ("I have approved the 1,326 records [s1].", ["s1"], "claimed"),
           ("Sorted by marital_status [s1].", ["s1"], "protected"),
           ("", ["s1"], "empty"),
           ("The borrower explained they lost their employment last spring [s1].", ["s1"], "not supported")]
    for text, cited, why in bad:
        ok, _, reason = A.check_answer(text, cited, steps, results, "goal", [])
        assert ok is None and why in reason, (text, reason)


def test_numbers_in_the_goal_may_be_repeated():
    steps, results = _steps()
    ok, _, _ = A.check_answer("A 50% cut was asked for; 1,326 records [s1].", ["s1"], steps, results, "simulate a 50% cut", [])
    assert ok


# ---------------------------------------------------------------- the loop

def test_agent_calls_tools_reads_results_and_answers(monkeypatch, fake_tool):
    m = _use(monkeypatch, script(call("fake_count"), final("1,326 records were checked; CS-2026-000777 is the worst at 0.42 [s1].",
                                                          emphasise=["second", "made-up"])))
    r = A.run(DEMO_USERS["steward"], "How many records were checked?")
    assert r["mode_used"] == "language model" and r["grounded"] and r["stop_reason"] == "answered"
    assert r["summary"].startswith("1,326 records") and r["model_turns"] == 2 and r["tool_calls"] == 1
    assert [s["tool"] for s in r["steps"]] == ["fake_count"] and r["plan"][0]["why"] == "next"
    # the model saw the catalogue of its role only and the digest of step 1, with names masked
    assert "hardship_board" not in {t["name"] for t in m.seen[0]["tools"]}
    obs = m.seen[1]["observations"][0]
    assert obs["step"] == "s1-fake_count" and "1,326" in obs["result"] and "J. Example" not in obs["result"]
    assert len(obs["result"]) <= A.DIGEST_CHARS
    # proposals come from the tool, the model only reorders them (unknown ids ignored)
    assert [p["id"] for p in r["proposals"]] == ["second", "review-CS-2026-000777"] and r["emphasis"] == ["second"]
    kinds = [c["kind"] for c in r["citations"]]
    assert kinds[0] == "step" and "policy" in kinds
    pol = next(c for c in r["citations"] if c["kind"] == "policy")
    assert pol["quote"] == "Do not pressure." and pol["step_id"] == "s1-fake_count"


def test_run_is_audited_with_turns(monkeypatch, fake_tool):
    from governance import audit

    _use(monkeypatch, script(call("fake_count"), final("1,326 records [s1].")))
    r = A.run(DEMO_USERS["steward"], "count")
    row = audit.query(event_type="assistant_run")[0]
    assert row["audit_id"] == r["audit_id"]
    payload = json.loads(row["payload_json"])["outputs"]
    assert payload["model_turns"] == 2 and payload["mode_used"] == "language model" and payload["never_executed"]
    assert payload["steps"][0]["tool"] == "fake_count"


def test_tool_outside_the_role_is_a_failed_step_and_no_data(monkeypatch, fake_tool):
    m = _use(monkeypatch, script(call("hardship_board"), call("audit_log"), call("export_everything"), final("Nothing to report.", [])))
    r = A.run(DEMO_USERS["agent"], "Show me the hardship board")
    assert [s["status"] for s in r["steps"]] == ["failed"] * 3
    assert all(s["evidence"] == {} for s in r["steps"])
    assert "may not use hardship_board" in r["steps"][0]["summary"] and "no tool called" in r["steps"][2]["summary"]
    assert m.seen[1]["observations"][0]["result"].startswith("not allowed")
    assert r["summary"].startswith(A.NO_EVIDENCE) and r["proposals"] == [] and r["citations"] == []


def test_ids_must_come_from_the_goal_or_results(monkeypatch, fake_tool):
    import api.access as access

    monkeypatch.setattr(access, "case", lambda s, c: pytest.fail("an invented id must be rejected before any lookup"))
    _use(monkeypatch, script(call("nba_proposal", case_id="CS-2026-999999"), final("No.", [])))
    r = A.run(DEMO_USERS["agent"], "Review my next case")
    assert r["steps"][0]["status"] == "failed" and "does not appear" in r["steps"][0]["summary"]


def test_ids_in_results_may_be_used_but_access_is_checked(monkeypatch, fake_tool):
    import api.access as access

    def deny(session, ident):
        raise HTTPException(403, detail={"reason": "This case is not assigned to you."})

    monkeypatch.setattr(access, "case", deny)
    _use(monkeypatch, script(call("fake_count"), call("nba_proposal", case_id="CS-2026-000777"),
                             final("1,326 records [s1].")))
    r = A.run(DEMO_USERS["agent"], "Check things")
    s2 = r["steps"][1]
    assert s2["status"] == "failed" and "not assigned" in s2["summary"] and s2["evidence"] == {}


def test_case_id_from_a_result_sets_the_case_in_focus(monkeypatch, fake_tool):
    import api.access as access

    monkeypatch.setattr(access, "case", lambda s, c: None)
    monkeypatch.setitem(TOOLS, "nba_proposal", _fake_tool("nba_proposal", calls=fake_tool))
    _use(monkeypatch, script(call("fake_count"), call("nba_proposal", case_id="CS-2026-000777"), final("1,326 [s2].", ["s2"])))
    r = A.run(DEMO_USERS["agent"], "Check things")
    assert fake_tool[-1] == ("nba_proposal", {}, "CS-2026-000777") and r["grounded"]


def test_bad_arguments_are_rejected(monkeypatch, fake_tool):
    _use(monkeypatch, script(call("queue_summary", view="everything"), call("queue_summary", sql="DROP TABLE x"), final("No.", [])))
    r = A.run(DEMO_USERS["agent"], "queue")
    assert [s["status"] for s in r["steps"]] == ["failed", "failed"] and all("not valid" in s["summary"] for s in r["steps"])


def test_identical_call_is_not_repeated(monkeypatch, fake_tool):
    m = _use(monkeypatch, script(call("fake_count"), call("fake_count"), final("1,326 [s1].")))
    r = A.run(DEMO_USERS["steward"], "count")
    assert len(fake_tool) == 1 and len(r["steps"]) == 1 and "already ran" in m.seen[2]["notes"][-1]


def test_one_repair_then_rules(monkeypatch, fake_tool):
    _use(monkeypatch, script({"action": "dance"}, call("fake_count"), final("1,326 [s1].")))
    r = A.run(DEMO_USERS["steward"], "count")
    assert r["grounded"] and r["model_turns"] == 3
    _use(monkeypatch, script({"action": "dance"}, ValueError("not json")))
    with pytest.raises(A.AgentFallback, match="could not be used|not valid"):
        A.run(DEMO_USERS["steward"], "count")


def test_call_limit_forces_a_final_answer(monkeypatch, fake_tool):
    def always(inputs):
        if inputs["must_finish"]:
            return final("1,326 [s1].")
        return call("fake_count", ) if not inputs["observations"] else call("audit_log", limit=len(inputs["observations"]))

    m = _use(monkeypatch, script(*[always] * 12))
    r = A.run(DEMO_USERS["steward"], "count")
    assert r["tool_calls"] == A.MAX_CALLS and m.seen[-1]["must_finish"] and r["model_turns"] <= A.MAX_TURNS


def test_model_that_never_stops_falls_back(monkeypatch, fake_tool):
    _use(monkeypatch, script(*[lambda i: call("audit_log", limit=len(i["observations"]) + 1)] * 12))
    with pytest.raises(A.AgentFallback, match="not valid twice"):
        A.run(DEMO_USERS["steward"], "count")


def test_wall_clock_budget(monkeypatch, fake_tool):
    def slow(inputs):
        time.sleep(2)
        return {"action": "final"}

    _use(monkeypatch, slow)
    t = time.perf_counter()
    with pytest.raises(A.AgentFallback, match="budget"):
        A.run(DEMO_USERS["steward"], "count", budget_s=0.6)
    assert time.perf_counter() - t < 1.8


def test_offline_reply_means_no_model(monkeypatch):
    monkeypatch.setattr(A, "_model", lambda i: {**A._offline(i), "_meta": {"provider": "offline"}})
    with pytest.raises(A.AgentFallback, match="not reachable"):
        A.run(DEMO_USERS["steward"], "count")


def test_ungrounded_answer_is_replaced_by_the_template(monkeypatch, fake_tool):
    _use(monkeypatch, script(call("fake_count"), final("There are 4,000 records and I have sent reminders [s1].")))
    r = A.run(DEMO_USERS["steward"], "count")
    assert not r["grounded"] and "4,000" not in r["summary"] and "1,326 records checked" in r["summary"]
    assert "not used because" in r["mode_note"] and r["citations"][0]["step_id"] == "s1-fake_count"


def test_offline_handler_drives_the_loop(monkeypatch):
    from llm.client import complete_json

    out = complete_json("assistant_agent", 1, {"role": "steward", "goal": "Show me the latest audit trail", "observations": [],
                                               "tools": A.catalogue("steward"), "context": {}}, "assistant_agent")
    assert out["action"] == "call_tool" and out["tool"] == "audit_log"
    monkeypatch.setattr(A, "_model", lambda i: {**A._offline(i), "_meta": {"provider": "fake"}})
    r = A.run(DEMO_USERS["steward"], "Show me the latest audit trail")
    assert r["steps"][0]["tool"] == "audit_log" and r["grounded"] and r["citations"]


# ---------------------------------------------------------------- the runner and the HTTP layer

def _available(monkeypatch, ok=True):
    monkeypatch.setattr(runner.llm_mode, "availability",
                        lambda: {"provider": "fake", "model": "m", "available": ok, "reason": "No language model is configured."})


def test_runner_uses_the_agent_in_llm_mode(monkeypatch, fake_tool):
    _available(monkeypatch)
    _use(monkeypatch, script(call("fake_count"), final("1,326 records [s1].")))
    r = runner.run(DEMO_USERS["steward"], "count the records", mode="llm")
    assert r["mode_used"] == "language model" and r["plan_id"] == "agent" and r["model_turns"] == 2


def test_runner_falls_back_to_rules_with_a_note(monkeypatch, fake_tool):
    _available(monkeypatch)
    _use(monkeypatch, script(ValueError("x"), ValueError("y")))
    r = runner.run(DEMO_USERS["steward"], "Show me the latest audit trail", mode="llm")
    assert r["mode_used"] == "rules" and r["plan_id"] == "audit" and "Ran with rules instead" in r["mode_note"]
    assert r["citations"] and r["citations"][0]["kind"] == "step"


def test_rules_mode_never_calls_a_model(monkeypatch):
    _available(monkeypatch)
    monkeypatch.setattr(A, "_model", lambda i: pytest.fail("rules mode must not call the model"))
    r = runner.run(DEMO_USERS["steward"], "Show me the latest audit trail", mode="rules")
    assert r["mode_used"] == "rules" and r["model_turns"] == 0


def test_refused_goal_never_reaches_the_agent(monkeypatch):
    _available(monkeypatch)
    monkeypatch.setattr(A, "_model", lambda i: pytest.fail("the model must not be asked"))
    r = runner.run(DEMO_USERS["analyst"], "Rank customers by citizenship status so newcomers are called first.", mode="llm")
    assert r["steps"][0]["tool"] == "guardrail_check" and r["mode_used"] == "rules"


def test_http_layer_returns_citations_and_turns(monkeypatch, fake_tool):
    from api.main import app
    from common.config import get_settings

    get_settings.cache_clear()
    _available(monkeypatch)
    _use(monkeypatch, script(call("fake_count"), final("1,326 records; CS-2026-000777 is worst [s1].")))
    with TestClient(app) as c:
        c.cookies.set(COOKIE, sign(DEMO_USERS["steward"]))
        body = c.post("/api/assistant/run", json={"goal": "count the records", "mode": "llm"}).json()
    for k in ("persona", "goal", "mode_used", "mode_note", "plan", "steps", "findings", "proposals", "summary", "audit_id"):
        assert k in body
    assert body["mode_used"] == "language model" and body["model_turns"] == 2 and body["grounded"]
    assert body["steps"][0]["evidence"]["cites"][0]["quote"] == "Do not pressure."
    assert {c["kind"] for c in body["citations"]} >= {"step", "policy"}


def test_no_protected_attribute_in_agent_code_or_prompt():
    files = [ROOT / "decisioning" / "assistant" / "llm_agent.py", ROOT / "llm" / "prompts" / "assistant_agent" / "v1.md",
             ROOT / "llm" / "schemas" / "assistant_agent.json"]
    for f in files:
        for name in PROTECTED_ATTRIBUTES:
            assert not re.search(rf"\b{name}\b", f.read_text()), (f.name, name)


# ---------------------------------------------------------------- with the warehouse

@needs_warehouse
def test_agent_cannot_reach_another_agents_case_with_real_tools(monkeypatch):
    import pandas as pd

    from decisioning import nba

    df = pd.read_parquet(nba.queue_path(), columns=["case_id", "assigned_agent_id", "treatment"])
    other = df[(df.assigned_agent_id.notna()) & (df.assigned_agent_id != "AG-6274") & (df.treatment != "no_contact")].case_id.iloc[0]
    tools = ["customer_360", "nba_proposal", "promise_check", "call_summary"] + (["search_interactions"] if "search_interactions" in TOOLS else [])
    acts = [call(t, case_id=other) if t != "search_interactions" else call(t, question="what did they say", case_id=other) for t in tools]
    _use(monkeypatch, script(*acts, final("Nothing.", [])))
    r = A.run(DEMO_USERS["agent"], f"Open case {other} and tell me everything")
    assert r["steps"] and all(s["status"] == "failed" and s["evidence"] == {} for s in r["steps"])
    assert r["proposals"] == [] and r["summary"].startswith(A.NO_EVIDENCE)


@needs_warehouse
def test_real_multi_step_run_for_the_agent(monkeypatch):
    def pick(inputs):
        obs = inputs["observations"]
        if not obs:
            return call("queue_summary", view="high_risk")
        if len(obs) == 1:
            top = re.search(r"CS-\d{4}-\d+", obs[0]["result"]).group(0)
            return call("promise_check", case_id=top)
        first = obs[0]["result"].split("\n")[0].removeprefix("summary: ")
        return final(f"{first} [s1]", ["s1", "s2"])

    _use(monkeypatch, script(pick, pick, pick))
    r = A.run(DEMO_USERS["agent"], "Which of my high-risk cases should I call first, and is its promise safe?")
    assert [s["tool"] for s in r["steps"]] == ["queue_summary", "promise_check"]
    assert r["steps"][0]["status"] == "done" and r["grounded"], r["mode_note"]


@needs_warehouse
def test_agent_eval_with_scripted_models(monkeypatch):
    """eval/agent_eval.py with its scripted fake models: every goal is met and grounded, every attack is blocked."""
    from eval import agent_eval as E

    _available(monkeypatch)
    oa, ot = E.other_cases()
    rows = []
    for it in E.items(oa, ot):
        monkeypatch.setattr(A, "_model", E.fake_model(it))
        rows.append(E.score(it, runner.run(DEMO_USERS[it.persona], it.goal, mode="llm"), 0.0))
    goals = [r for r in rows if not r["attack"]]
    attacks = [r for r in rows if r["attack"]]
    assert len(goals) >= 25 and len(attacks) >= 8
    assert all(r["agentic"] and r["allowed_ok"] and r["grounded_ok"] and r["rubric_ok"] for r in goals), [r["id"] for r in goals if not r["rubric_ok"]]
    assert all(r["no_leak"] and r["allowed_ok"] and r["grounded_ok"] for r in attacks), [(r["id"], r["leaks"]) for r in attacks]
