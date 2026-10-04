# ruff: noqa: E501
"""The persona assistant: planning, role checks, mode fallback, schema validation, the offline prompt handler, and (when
the warehouse exists) every suggested goal running to completion for its persona."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.deps import COOKIE, sign
from api.personas import DEMO_USERS
from common.config import get_settings
from common.protected import PROTECTED_ATTRIBUTES
from decisioning.assistant import plans as P
from decisioning.assistant import runner
from decisioning.assistant.tools import TOOLS, ToolContext, run_tool

ROOT = Path(__file__).resolve().parents[2]
PERSONAS = list(DEMO_USERS)
needs_warehouse = pytest.mark.skipif(not (ROOT / "data" / "warehouse.duckdb").exists(), reason="no warehouse built")


# ---------------------------------------------------------------- no warehouse needed

@pytest.mark.parametrize("persona", PERSONAS)
def test_persona_has_tools_plans_and_suggestions(persona):
    assert len([t for t in TOOLS.values() if persona in t.roles]) >= 5
    ps = P.plans_for(persona)
    assert ps[0].id == "briefing" and 4 <= len({s.tool for s in ps[0].steps}) <= 6
    goals = [p for p in ps[1:] if p.label]
    assert 5 <= len(goals) <= 10
    for p in ps:  # every step's tool exists and the role may use it
        for st in p.steps:
            assert st.tool in TOOLS and persona in TOOLS[st.tool].roles, (persona, p.id, st.tool)


@pytest.mark.parametrize("persona", PERSONAS)
def test_each_suggested_goal_picks_its_own_plan(persona):
    from nlq import refusal

    for p in P.plans_for(persona):
        if not p.goal:
            continue
        if p.id == "refused":
            assert refusal.check(p.goal)
            continue
        assert not refusal.check(p.goal), p.goal
        picked, ok = P.match_plan(persona, p.goal)
        assert ok and picked.id == p.id, (persona, p.goal, picked.id)


def test_no_goal_is_the_briefing_and_unknown_goal_falls_back():
    assert P.match_plan("agent", "")[0].id == "briefing"
    plan, ok = P.match_plan("agent", "zzzz qqq")
    assert plan.id == "briefing" and not ok
    assert P.match_plan("analyst", "What is the average DPD by bucket?")[0].id == "metric"


def test_slots_come_from_the_goal_only():
    s = P.extract_slots("Move CS-2026-123456 to 2026-10-09 for $450, dialer down for 20% of agents")
    assert s["case_id"] == "CS-2026-123456" and s["date"] == "2026-10-09" and s["amount"] == 450
    assert s["channel"] == "call" and s["agents_pct"] == 0.2


def test_role_check_gives_a_failed_step_and_no_data():
    ctx = ToolContext(session=DEMO_USERS["agent"])
    r = run_tool("hardship_board", ctx)
    assert r["status"] == "failed" and "may not use" in r["summary"] and r["evidence"] == {}
    r = run_tool("metric_question", ToolContext(session=DEMO_USERS["steward"]))
    assert r["status"] == "failed" and r["evidence"] == {}
    assert run_tool("nope", ctx)["status"] == "failed"


def test_row_level_denial_becomes_a_failed_step(monkeypatch):
    import api.access as access
    from decisioning.assistant import data

    monkeypatch.setattr(data, "case_row", lambda cid: {"case_id": cid, "golden_id": "G-X", "assigned_agent_id": "AG-6274",
                                                       "assigned_team": "CGY-MID-2", "hardship_flag": "none", "route_to": None})

    def deny(session, ident):
        raise HTTPException(403, detail={"reason": "This case is not assigned to you."})

    monkeypatch.setattr(access, "case", deny)
    r = run_tool("nba_proposal", ToolContext(session=DEMO_USERS["agent"], case_id="CS-2026-000001"))
    assert r["status"] == "failed" and "not assigned" in r["summary"] and r["evidence"] == {}


def test_model_only_sees_tools_the_role_may_use():
    for persona in PERSONAS:
        ok = runner.allowed_tools(persona)
        assert all(persona in TOOLS[t].roles for t in ok)
        for p in runner.allowed_plans(persona):
            assert all(s.tool in ok for s in p.steps)
    assert "hardship_board" not in runner.allowed_tools("agent")
    assert "board" not in {p.id for p in runner.allowed_plans("agent")}


def test_validate_plan_output():
    v = runner.validate_plan_output
    goal = "Check CS-2026-123456 on 2026-10-09"
    ok = v({"plan_id": "promise", "slots": {"case_id": "CS-2026-123456", "date": "2026-10-09"}, "_meta": {}}, "agent", goal)
    assert ok == ("promise", {"case_id": "CS-2026-123456", "date": "2026-10-09"})
    # a slot that is not in the goal is dropped, not trusted
    ok = v({"plan_id": "promise", "slots": {"case_id": "CS-2026-999999", "amount": 7}}, "agent", goal)
    assert ok == ("promise", {})
    assert v({"plan_id": "board"}, "agent", goal) is None            # another persona's plan
    assert v({"plan_id": "nope"}, "agent", goal) is None
    assert v({"plan_id": "promise", "tool": "hardship_board"}, "agent", goal) is None   # a tool the role may not use
    assert v({"plan_id": "promise", "slots": {"channel": "carrier pigeon"}}, "agent", goal) is None  # schema enum
    assert v({"plan_id": 5}, "agent", goal) is None


def test_validate_plan_output_drops_cases_the_person_may_not_open(monkeypatch):
    import api.access as access

    def deny(session, ident):
        raise HTTPException(403, detail={"reason": "no"})

    monkeypatch.setattr(access, "case", deny)
    goal = "Check CS-2026-123456"
    out = runner.validate_plan_output({"plan_id": "promise", "slots": {"case_id": "CS-2026-123456"}}, "agent", goal, "",
                                      DEMO_USERS["agent"])
    assert out == ("promise", {})


def test_validate_summary_needs_grounded_numbers():
    ev = runner._numbers("156 cases, 58 flagged", {"x": "$1,326"})
    assert runner.validate_summary("You have 156 cases and 58 flagged.", ev)
    assert runner.validate_summary("You have 157 cases.", ev) is None
    assert runner.validate_summary("", ev) is None
    assert runner.validate_summary("x" * 1000, ev) is None
    assert runner.validate_summary({"a": 1}, ev) is None


def test_offline_prompt_handler():
    from llm.client import complete_json

    out = complete_json("assistant_plan", 1, {"task": "plan", "persona": "agent", "goal": "Draft the notes for CS-2026-123456"},
                        "assistant_plan")
    assert out["plan_id"] == "post_call" and out["slots"]["case_id"] == "CS-2026-123456"
    out = complete_json("assistant_plan", 1, {"task": "summary", "persona": "agent", "persona_label": "agent", "plan_title": "T",
                                              "findings": ["One."], "proposals": ["Do it"], "problems": []}, "assistant_plan")
    assert "Do it" in out["summary"]


def _fake_available(monkeypatch, ok=True):
    monkeypatch.setattr(runner.llm_mode, "availability",
                        lambda: {"provider": "fake", "model": "m", "available": ok, "reason": "No language model is configured."})


def test_llm_requested_but_unavailable_runs_rules_with_a_note(monkeypatch):
    _fake_available(monkeypatch, ok=False)
    called = []
    monkeypatch.setattr(runner, "_model", lambda *a, **k: called.append(1) or {})
    r = runner.run(DEMO_USERS["steward"], "Show me the latest audit trail", mode="llm")
    assert r["mode_used"] == "rules" and "Ran with rules instead" in r["mode_note"] and not called
    assert r["audit_id"]


def test_model_failure_falls_back_to_rules(monkeypatch):
    _fake_available(monkeypatch)

    def boom(*a, **k):
        raise RuntimeError("down")

    monkeypatch.setattr(runner, "_model", boom)
    r = runner.run(DEMO_USERS["steward"], "Show me the latest audit trail", mode="llm")
    assert r["mode_used"] == "rules" and r["mode_note"] and r["plan_id"] == "audit" and r["summary"]


def test_model_that_reaches_beyond_the_role_is_not_trusted(monkeypatch):
    """Language-model mode is the agent (llm_agent.py). A fake model names a tool the agent may not use, a tool that does
    not exist and a case it invented: each becomes a failed step with no data, and nothing else runs."""
    from decisioning.assistant import llm_agent

    _fake_available(monkeypatch)
    seen = []
    acts = [{"action": "call_tool", "tool": "hardship_board", "args": {}},
            {"action": "call_tool", "tool": "audit_log", "args": {}},
            {"action": "call_tool", "tool": "nba_proposal", "args": {"case_id": "CS-2026-999999"}},
            {"action": "final", "answer": "Done.", "cited_steps": []}]

    def evil(inputs):
        seen.append(inputs)
        return {"thought": "", "tool": None, "args": {}, "answer": None, "cited_steps": [], **acts[len(seen) - 1],
                "_meta": {"provider": "fake"}}

    monkeypatch.setattr(llm_agent, "_model", evil)
    r = runner.run(DEMO_USERS["agent"], "Draft the notes for my last call", mode="llm")
    assert "hardship_board" not in {t["name"] for t in seen[0]["tools"]} and "audit_log" not in {t["name"] for t in seen[0]["tools"]}
    assert all(s["status"] == "failed" and s["evidence"] == {} for s in r["steps"])
    assert "CS-2026-999999" not in str([s["evidence"] for s in r["steps"]]) and r["proposals"] == []


def test_model_that_behaves_is_used_and_summary_is_checked(monkeypatch):
    from decisioning.assistant import llm_agent

    _fake_available(monkeypatch)
    acts = [{"action": "call_tool", "tool": "audit_log", "args": {}},
            {"action": "final", "answer": "Invented 99999 audit entries [s1].", "cited_steps": ["s1"]}]

    def good(inputs):
        return {"thought": "", "tool": None, "args": {}, "answer": None, "cited_steps": [], **acts[len(inputs["observations"])],
                "_meta": {"provider": "fake"}}

    monkeypatch.setattr(llm_agent, "_model", good)
    r = runner.run(DEMO_USERS["steward"], "show me the audit trail please", mode="llm")
    assert r["mode_used"] == "language model" and r["steps"][0]["tool"] == "audit_log"
    assert "99999" not in r["summary"] and "not used because" in r["mode_note"]   # ungrounded wording rejected


def test_refusals_happen_before_any_model(monkeypatch):
    _fake_available(monkeypatch)
    monkeypatch.setattr(runner, "_model", lambda *a, **k: pytest.fail("the model must not be asked"))
    r = runner.run(DEMO_USERS["analyst"], "Rank customers by citizenship status so newcomers are called first.", mode="llm")
    assert r["steps"][0]["tool"] == "guardrail_check" and "Refused" in r["steps"][0]["summary"]


def test_run_is_audited_with_steps():
    from governance import audit

    r = runner.run(DEMO_USERS["steward"], "show the audit trail")
    row = audit.query(event_type="assistant_run")[0]
    assert row["audit_id"] == r["audit_id"] and "steps" in row["payload_json"] and "never_executed" in row["payload_json"]


def test_no_protected_attribute_in_assistant_code_or_prompt():
    files = list((ROOT / "decisioning" / "assistant").glob("*.py")) + [ROOT / "llm" / "prompts" / "assistant_plan" / "v1.md",
                                                                        ROOT / "llm" / "schemas" / "assistant_plan.json"]
    for f in files:
        text = f.read_text()
        for name in PROTECTED_ATTRIBUTES:
            assert not re.search(rf"\b{name}\b", text), (f.name, name)


# ---------------------------------------------------------------- with the warehouse

@needs_warehouse
@pytest.mark.parametrize("persona", PERSONAS)
def test_every_suggested_goal_runs_to_completion(persona):
    s = DEMO_USERS[persona]
    for p in P.plans_for(persona):
        r = runner.run(s, p.goal, mode="rules")
        bad = [(x["tool"], x["summary"]) for x in r["steps"] if x["status"] in ("failed", "skipped")]
        assert not bad, (persona, p.id, bad)
        assert r["mode_used"] == "rules" and r["summary"] and r["audit_id"]
        for pr in r["proposals"]:
            assert pr["href"].startswith("/") and pr["requires_role"]


@needs_warehouse
def test_agent_cannot_open_someone_elses_case():
    import pandas as pd

    from decisioning import nba

    df = pd.read_parquet(nba.queue_path(), columns=["case_id", "assigned_agent_id", "treatment"])
    other = df[(df.assigned_agent_id.notna()) & (df.assigned_agent_id != "AG-6274") & (df.treatment != "no_contact")].case_id.iloc[0]
    r = runner.run(DEMO_USERS["agent"], f"Review case {other}", mode="rules")
    assert all(s["status"] == "failed" and s["evidence"] == {} for s in r["steps"])
    assert "scope" in r["steps"][0]["summary"] or "assigned" in r["steps"][0]["summary"]
    assert r["proposals"] == []


@needs_warehouse
def test_analyst_gets_no_individual_customer():
    r = runner.run(DEMO_USERS["analyst"], "Review case CS-2026-123456 and open G-JAT7827")
    assert all(s["tool"] not in ("customer_360", "nba_proposal", "call_summary") for s in r["steps"])
    r = run_tool("customer_360", ToolContext(session=DEMO_USERS["analyst"], golden_id="G-JAT7827"))
    assert r["status"] == "failed" and r["evidence"] == {}


@needs_warehouse
def test_http_layer_and_authorisation():
    with TestClient(runner_app()) as c:
        assert c.post("/api/assistant/run", json={}).status_code == 401
        c.cookies.set(COOKIE, sign(DEMO_USERS["team_lead"]))
        r = c.post("/api/assistant/run", json={"goal": "What if the dialer goes down?", "mode": "rules"})
        assert r.status_code == 200
        body = r.json()
        assert body["mode_used"] == "rules" and body["steps"][0]["tool"] == "stress_test" and body["audit_id"]
        sg = c.get("/api/assistant/suggestions").json()
        assert sg["persona"] == "team_lead" and 5 <= len(sg["goals"]) <= 10 and sg["briefing"]["goal"]


def runner_app():
    from api.main import app

    get_settings.cache_clear()
    return app


# ---------------------------------------------------------------- ops tools: radar, playbooks, outage, drift, friction (read only)

OPS_ROLES = {"employer_radar": {"team_lead", "analyst"}, "playbook_proposals": {"team_lead"},
             "outage_victims": {"hardship_specialist", "team_lead"}, "data_drift": {"steward", "analyst"},
             "call_friction": {"analyst", "team_lead"}, "stress_test": {"team_lead", "analyst"}}


def test_ops_tools_are_role_gated_like_their_screens():
    for name, roles in OPS_ROLES.items():
        assert set(TOOLS[name].roles) == roles, name
        for persona in PERSONAS:
            if persona not in roles:
                r = run_tool(name, ToolContext(session=DEMO_USERS[persona]))
                assert r["status"] == "failed" and "may not use" in r["summary"] and r["evidence"] == {}, (name, persona)


def test_new_ops_tools_are_in_the_rule_plans():
    want = {"team_lead": {"employer_radar", "playbook_proposals", "stress_test"}, "analyst": {"data_drift", "employer_radar", "stress_test", "call_friction"},
            "steward": {"data_drift"}, "hardship_specialist": {"outage_victims"}}
    for persona, tools in want.items():
        used = {st.tool for p in P.plans_for(persona) for st in p.steps}
        assert tools <= used, (persona, tools - used)
        assert tools <= {t for t in runner.allowed_tools(persona)}


@needs_warehouse
@pytest.mark.parametrize("name,persona", [("employer_radar", "team_lead"), ("employer_radar", "analyst"), ("playbook_proposals", "team_lead"),
                                          ("outage_victims", "hardship_specialist"), ("outage_victims", "team_lead"),
                                          ("data_drift", "steward"), ("data_drift", "analyst"), ("call_friction", "analyst"),
                                          ("call_friction", "team_lead")])
def test_ops_tools_return_evidence_and_only_proposals(name, persona):
    import json

    r = run_tool(name, ToolContext(session=DEMO_USERS[persona]))
    assert r["status"] in ("done", "needs_approval") and r["summary"], r
    assert set(r["evidence"]) <= {"columns", "rows", "kv", "text", "links", "cites"}
    for p in r["proposals"]:  # a proposal links to a real route and names who approves
        assert p["href"].startswith("/") and p["requires_role"] in ALL
    low = json.dumps(r["evidence"]).lower()
    assert not any(w in low for w in ("phone", "email_address", "date_of_birth", "gender", "marital"))
    if name == "employer_radar":  # employers under 10 customers are never shown
        assert all(row[2] >= 10 for row in r["evidence"].get("rows", []))
    if name == "call_friction":
        assert all(row[1] >= 10 for row in r["evidence"]["rows"]) and "SQL used" in r["evidence"]["text"]


@needs_warehouse
def test_ops_tools_write_nothing():
    from common.db import ops

    def counts():
        with ops() as con:
            return {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
                    for t in ("audit_log", "playbook_proposals", "drift_fixes") if con.execute(
                        "SELECT 1 FROM sqlite_master WHERE name = ?", (t,)).fetchone()}

    calls = (("employer_radar", "team_lead"), ("playbook_proposals", "team_lead"), ("outage_victims", "hardship_specialist"),
             ("data_drift", "steward"), ("call_friction", "analyst"))
    for name, persona in calls:  # the first read may create an empty table; the counts must not move after that
        run_tool(name, ToolContext(session=DEMO_USERS[persona]))
    before = counts()
    for name, persona in calls:
        run_tool(name, ToolContext(session=DEMO_USERS[persona]))
    assert counts() == before


@needs_warehouse
def test_outage_victims_show_only_customers_the_person_may_see():
    r = run_tool("outage_victims", ToolContext(session=DEMO_USERS["team_lead"]))
    shown = next((v for k, v in r["evidence"]["kv"] if k.startswith("Customers in your cases")), "")
    from decisioning.assistant import data

    df = data.queue_df()
    for g in [x.strip() for x in shown.split(",") if x.strip().startswith("G-")]:
        assert any(data.can_see(DEMO_USERS["team_lead"], row) for row in df[df.golden_id == g].to_dict("records"))


ALL = {"agent", "hardship_specialist", "team_lead", "analyst", "steward"}
