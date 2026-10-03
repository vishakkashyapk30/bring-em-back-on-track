# ruff: noqa: E501
"""The guided demo: stage structure (no warehouse needed) and, with the warehouse, the sample customer rules, access
and the response time."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.deps import COOKIE, sign
from api.personas import DEMO_USERS
from decisioning.assistant import data, journey
from decisioning.assistant.tools import TOOLS

ROOT = Path(__file__).resolve().parents[2]
needs_warehouse = pytest.mark.skipif(not (ROOT / "data" / "warehouse.duckdb").exists(), reason="no warehouse built")
SAMPLE = {"case_id": "CS-2026-000001", "golden_id": "G-TEST001", "name": "T. Customer"}


@pytest.mark.parametrize("persona", list(DEMO_USERS))
def test_stage_structure(persona):
    title, intro, stages = journey._stages(persona, SAMPLE if persona != "analyst" else None)
    assert title and intro and 6 <= len(stages) <= 8
    for st in stages:
        assert st["screen"].startswith("/") and st["narrative"] and st["why_it_matters"]
        if st["tool"]:
            assert st["tool"] in TOOLS and persona in TOOLS[st["tool"]].roles, (persona, st["id"])
    if persona in ("agent", "hardship_specialist", "team_lead"):
        assert any(st["human_step"] for st in stages)


def test_stage_without_tool_is_a_human_step():
    st = journey._stage("x", "t", "n", "/queue", "w", None, None, "Approve it")
    out = journey._run_stage("agent", st, SAMPLE)
    assert out["status"] == "needs_approval" and out["evidence"] == {} and out["summary"] == "Approve it"


@needs_warehouse
def test_sample_customer_is_open_to_the_demo_agent_and_lead():
    data.clear_caches()
    c = journey.sample_customer()
    row = data.case_row(c["case_id"])
    assert row["assigned_agent_id"] == "AG-6274" and row["assigned_team"] == "CGY-MID-2"
    assert c["all_criteria"] and row["status"] == "scheduled" and row["hardship_flag"] != "none"
    assert row["treatment"] in ("plan_offer", "specialist_referral")
    assert data.can_see(DEMO_USERS["agent"], row) and data.can_see(DEMO_USERS["team_lead"], row)
    assert data.can_see(DEMO_USERS["hardship_specialist"], row)
    assert journey.sample_customer() == c    # cached and deterministic


@needs_warehouse
def test_journeys_over_http_are_live_authorised_and_fast():
    from api.main import app

    data.clear_caches()
    with TestClient(app) as c:
        assert c.get("/api/demo/journey/agent").status_code == 401
        for persona in DEMO_USERS:
            c.cookies.set(COOKIE, sign(DEMO_USERS[persona]))
            assert c.get(f"/api/demo/journey/{persona}").status_code == 200   # warms caches
            data._ttl.pop(("journey", persona), None)            # next call recomputes, with warm sub-caches
            t = time.perf_counter()
            r = c.get(f"/api/demo/journey/{persona}")
            dt = time.perf_counter() - t
            j = r.json()
            assert j["persona"] == persona and 6 <= len(j["stages"]) <= 8 and dt < 1.5, (persona, dt)
            live = [s for s in j["stages"] if s["tool"]]
            assert all(s["status"] in ("done", "needs_approval") for s in live), [(s["id"], s["summary"]) for s in live]
            if persona != "analyst":
                assert j["customer"]["golden_id"] and any(j["customer"]["golden_id"] in s["screen"] for s in j["stages"])
            else:
                assert j["customer"] is None
        # a persona can only open its own journey
        c.cookies.set(COOKIE, sign(DEMO_USERS["agent"]))
        assert c.get("/api/demo/journey/team_lead").status_code == 403
        assert c.get("/api/demo/journey/nobody").status_code == 404
