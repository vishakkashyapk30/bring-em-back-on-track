# ruff: noqa: E501
"""'Waiting for you' inbox: role scoping, read-only, sources that do not exist are reported, not faked."""

import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api.schemas.common import Session
from api.services import inbox
from common.db import ops


def S(role, user="U-1", team=None):
    return Session(user_id=user, role=role, team_id=team, display_name="x")


AGENT = S("agent", "AG-1", "CGY-MID-2")
LEAD = S("team_lead", "AG-9", "CGY-MID-2")
SPEC = S("hardship_specialist", "AG-5", "MTL-HARD-2")
STEWARD = S("steward", "DS-1")
ANALYST = S("analyst", "AN-1")


def _row(case, agent, team, **kw):
    r = {"case_id": case, "golden_id": f"G-{case}", "name": "Pat Doe", "treatment": "plan_offer", "channel": "call",
         "priority": 1.0, "route_to": None, "review_mode": "individual", "headline": "h", "status": "scheduled",
         "assigned_agent_id": agent, "assigned_team": team, "plan_date": "2026-09-28", "hardship_flag": "none",
         "vulnerable": False, "product": "card", "dpd": 40, "p_break": 0.5}
    r.update(kw)
    return r


@pytest.fixture
def queue(tmp_path, monkeypatch):
    """A small nightly queue file and 'live' data for the queue-based sources."""
    from decisioning import nba

    rows = [
        _row("C1", "AG-1", "CGY-MID-2", priority=3.0),
        _row("C2", "AG-1", "CGY-MID-2", priority=2.0),
        _row("C3", "AG-2", "CGY-MID-2"),                                     # someone else's case
        _row("C4", "AG-1", "CGY-MID-2", review_mode="batch", treatment="reminder", channel="sms"),  # batch, not one by one
        _row("C5", "AG-7", "MTL-HARD-1", route_to="hardship_specialist"),    # specialist, same site
        _row("C6", "AG-8", "CGY-LATE-1", route_to="hardship_specialist"),    # specialist, other site
    ]
    p = tmp_path / "nba_queue.parquet"
    pd.DataFrame(rows).to_parquet(p)
    monkeypatch.setattr(nba, "queue_path", lambda: p)
    monkeypatch.setattr(inbox, "live_data", lambda: True)
    return p


def test_agent_sees_only_their_own_undecided_one_by_one_actions(queue):
    with ops() as con:
        con.execute("INSERT INTO nba_decisions (case_id, proposed_json, decision, user_id) VALUES ('C2', '{}', 'approve', 'AG-1')")
    g = inbox.nba_actions(AGENT)
    assert g.count == 1 and [i.subject_id for i in g.items] == ["C1"]
    assert g.items[0].link == "/customers/G-C1" and "one by one" in g.items[0].reason


def test_specialist_sees_hardship_cases_at_their_site_only(queue):
    g = inbox.nba_actions(SPEC)
    assert [i.subject_id for i in g.items] == ["C5"]


def test_team_lead_sees_only_their_teams_batches(queue):
    with ops() as con:
        for b in ("B-20260928-SMS-REM-CGY-MID-2", "B-20260928-SMS-REM-CGY-MID-3"):
            con.execute("INSERT INTO batches (batch_id, kind, strategy_code, items_json, sample_json) VALUES (?,?,?,?,?)",
                        (b, "digital_reminders", "reminder:sms", json.dumps(["C1", "C2"]), json.dumps(["C1"])))
    g = inbox.batches(LEAD)
    assert g.count == 1 and g.items[0].id.endswith("CGY-MID-2")
    assert "2% sample" in g.items[0].reason and g.items[0].link == "/team"


def test_override_review_threshold_is_per_agent_on_the_team(monkeypatch):
    monkeypatch.setattr(inbox, "live_data", lambda: True)
    monkeypatch.setattr(inbox, "_q", lambda sql, params=None: [{"agent_id": "AG-1", "agent_display_name": "A. One"},
                                                               {"agent_id": "AG-2", "agent_display_name": "B. Two"}])
    prop = json.dumps({"action": {"treatment": "reminder", "channel": "sms"}})
    final = json.dumps({"treatment": "plan_offer", "channel": "call"})
    with ops() as con:
        for uid, overrides in (("AG-1", 3), ("AG-2", 1), ("AG-3", 6)):  # AG-3 is not on the team
            for i in range(6):
                d = "override" if i < overrides else "approve"
                con.execute("INSERT INTO nba_decisions (case_id, proposed_json, decision, final_json, user_id) VALUES (?,?,?,?,?)",
                            (f"{uid}-{i}", prop, d, final if d == "override" else None, uid))
    g = inbox.override_reviews(LEAD)
    assert [i.subject_id for i in g.items] == ["AG-1"]
    assert "3 of 6" in g.items[0].title and "25%" in g.items[0].reason


def test_steward_inbox_lists_drift_fixes_and_failing_contract_tests(tmp_path, monkeypatch):
    from common.config import get_settings
    from governance import drift

    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    monkeypatch.setenv("FORCE_FIXTURES", "true")
    get_settings.cache_clear()
    (tmp_path / "contract_tests.json").write_text(json.dumps({"metadata": {"generated_at": "2026-10-03T10:00:00Z"}, "results": [
        {"unique_id": "test.collections360.not_null_c360_customer_golden_id.1", "status": "fail", "failures": 12},
        {"unique_id": "test.collections360.unique_c360_customer_golden_id.2", "status": "pass"},
        {"unique_id": "model.collections360.c360_customer", "status": "success"}]}))
    drift.store_fix({"fix_id": "FIX-1", "table": "contact_history", "change": {}, "description": "channel renamed",
                     "diff": "", "explanation": "", "drafted_by": "rules"})
    out = inbox.build(STEWARD)
    by = {g.type: g for g in out.groups}
    assert by["drift_fixes"].count == 1 and by["drift_fixes"].items[0].link == "/steward/drift"
    assert by["contract_tests"].count == 1 and "12 rows" in by["contract_tests"].items[0].reason
    assert any(n.source == "Identity grey-band pairs" for n in out.not_available)  # no warehouse in this test
    assert out.total == 2 and len(out.top) == 2


def test_analyst_has_nothing_to_approve_and_sees_only_their_own_proposals():
    out = inbox.build(ANALYST)
    assert out.total == 0 and next(g for g in out.groups if g.type == "own_proposals").count == 0
    with ops() as con:
        con.execute("CREATE TABLE proposals (proposal_id TEXT, title TEXT, status TEXT, author_id TEXT, addressed_to TEXT, created_ts TEXT)")
        con.executemany("INSERT INTO proposals VALUES (?,?,?,?,?,?)", [
            ("P1", "Try SMS first in 1-30", "pending", "AN-1", "team_lead", "2026-10-01T00:00:00Z"),
            ("P2", "Someone else's", "pending", "AN-2", "team_lead", "2026-10-01T00:00:00Z"),
            ("P3", "Done already", "accepted", "AN-1", "team_lead", "2026-10-02T00:00:00Z")])
    out = inbox.build(ANALYST)
    g = next(g for g in out.groups if g.type == "own_proposals")
    assert g.informational and {i.id for i in g.items} == {"proposal:P1", "proposal:P3"} and out.total == 0
    lead = inbox.strategy_proposals(LEAD)
    assert {i.id for i in lead.items} == {"proposal:P1", "proposal:P2"}  # pending ones addressed to team leads


def test_strategy_tests_in_the_playbook_store_go_to_team_leads_and_back_to_their_analyst():
    from decisioning import playbooks

    playbooks.store([{"proposal_id": "PB-T1", "playbook": "strategy_test", "kind": "strategy_test", "subject_id": "product:card",
                      "title": "Test strategy EARLY-SMS on card cases", "detail": "d", "payload": {"proposed_by": "AN-1"}},
                     {"proposal_id": "PB-R1", "playbook": "employer_radar", "kind": "hold", "subject_id": "EMP-0A1B2C3D",
                      "title": "Hold pressure at EMP-0A1B2C3D", "detail": "d", "payload": {}}])
    lead = {g.type: g for g in inbox.build(LEAD).groups}
    assert [i.id for i in lead["strategy_proposals"].items] == ["proposal:PB-T1"]
    assert lead["strategy_proposals"].items[0].link == "/team?tab=playbooks"
    assert [i.id for i in lead["playbook_proposals"].items] == ["playbook:PB-R1"]  # a test is not listed twice
    mine = next(g for g in inbox.build(ANALYST).groups if g.type == "own_proposals")
    assert [i.id for i in mine.items] == ["proposal:PB-T1"] and mine.items[0].reason == "Status: pending."
    assert next(g for g in inbox.build(S("analyst", "AN-2")).groups if g.type == "own_proposals").count == 0


def test_specialist_reports_the_missing_sign_off_store():
    out = inbox.build(SPEC)
    assert any("above an agent's level" in n.source for n in out.not_available)


@pytest.fixture
def client(monkeypatch):
    from common.config import get_settings

    monkeypatch.setenv("FORCE_FIXTURES", "true")  # no warehouse reads: fast and the same on every machine
    get_settings.cache_clear()
    from api.main import app

    inbox.clear_cache()
    return TestClient(app)


@pytest.mark.parametrize("role", ["agent", "hardship_specialist", "team_lead", "analyst", "steward"])
def test_every_role_gets_an_inbox_and_matching_counts_and_nothing_is_written(client, role):
    client.post("/api/auth/session", params={"role": role})
    with ops() as con:
        before = con.execute("SELECT count(*) FROM audit_log").fetchone()[0]
    r = client.get("/api/inbox")
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == role and len(body["top"]) <= 3
    c = client.get("/api/inbox/counts").json()
    assert c["total"] == body["total"]
    with ops() as con:
        assert con.execute("SELECT count(*) FROM audit_log").fetchone()[0] == before


def test_inbox_needs_a_session(client):
    assert client.get("/api/inbox").status_code == 401
    assert client.get("/api/inbox/counts").status_code == 401
