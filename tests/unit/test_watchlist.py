# ruff: noqa: E501
"""Saved watchlist: pins authorised like viewing, audited pins and unpins, and 'what changed since you last looked'."""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api import access
from api.schemas.common import Session
from api.services import watchlist as wl
from common.db import ops


def S(role, user="U-1", team=None):
    return Session(user_id=user, role=role, team_id=team, display_name="x")


AGENT = S("agent", "AG-1", "T-1")
LEAD = S("team_lead", "AG-9", "T-1")
ANALYST = S("analyst", "AN-1")
STEWARD = S("steward", "DS-1")


@pytest.fixture(autouse=True)
def offline_data(monkeypatch):
    """No warehouse reads (facts come from the ops store only); row scope enforced through access._count."""
    monkeypatch.setattr(wl, "live_data", lambda: False)
    monkeypatch.setattr(access, "live_data", lambda: True)
    monkeypatch.setattr(access, "_count", lambda s, where, param: int(param.endswith("-MINE")))
    wl._ready_paths.clear()


def _audit(event):
    with ops() as con:
        return con.execute("SELECT * FROM audit_log WHERE event_type = ?", (event,)).fetchall()


def test_pin_and_unpin_are_audited_and_a_repeat_pin_writes_nothing():
    r = wl.pin(AGENT, "customer", "G-1-MINE")
    assert r.pinned and r.audit_id
    row = _audit("watch_pin")[0]
    assert (row["user_id"], row["entity_type"], row["entity_id"]) == ("AG-1", "customer", "G-1-MINE")
    assert wl.pin(AGENT, "customer", "G-1-MINE").audit_id is None and len(_audit("watch_pin")) == 1
    assert wl.pins(AGENT) == [{"kind": "customer", "subject_id": "G-1-MINE"}]
    u = wl.unpin(AGENT, "customer", "G-1-MINE")
    assert not u.pinned and u.audit_id and len(_audit("watch_unpin")) == 1
    assert wl.pins(AGENT) == []


def test_an_agent_cannot_pin_another_agents_customer_or_case():
    for kind in ("customer", "case", "identity"):
        with pytest.raises(HTTPException) as e:
            wl.pin(AGENT, kind, "G-2-THEIRS")
        assert e.value.status_code == 403
    with pytest.raises(HTTPException) as e:
        wl.pin(AGENT, "agent", "AG-2")
    assert e.value.status_code == 403
    assert wl.pins(AGENT) == [] and _audit("watch_pin") == []


def test_an_agent_may_follow_their_own_work():
    assert wl.pin(AGENT, "agent", "AG-1").pinned
    assert wl.pin(AGENT, "case", "CS-1-MINE").pinned


def test_analysts_pin_aggregate_kinds_only():
    for kind, sid in (("customer", "G-1-MINE"), ("case", "C-1-MINE"), ("agent", "AG-1"), ("identity", "G-1-MINE")):
        with pytest.raises(HTTPException) as e:
            wl.pin(ANALYST, kind, sid)
        assert e.value.status_code == 403
    assert wl.pin(ANALYST, "cohort", "bucket:31-60").pinned
    assert wl.pin(ANALYST, "employer", "EMP-0A1B2C3D").pinned
    assert wl.pin(ANALYST, "data_product", "gold.c360_customer").pinned
    with pytest.raises(HTTPException) as e:
        wl.pin(ANALYST, "cohort", "gender_code:F")  # only allowlisted case columns can define a cohort
    assert e.value.status_code == 422


def test_stewards_follow_identity_and_data_products_not_customers():
    with pytest.raises(HTTPException) as e:
        wl.pin(STEWARD, "customer", "G-1-MINE")
    assert e.value.status_code == 403
    assert wl.pin(STEWARD, "identity", "G-9-ANY").pinned
    assert wl.pin(STEWARD, "data_product", "silver.contact_history").pinned


def test_a_team_lead_pins_only_agents_on_their_team(monkeypatch):
    monkeypatch.setattr(wl, "live_data", lambda: True)
    monkeypatch.setattr(wl, "_q", lambda sql, params=None: [{"x": 1}] if "silver.agents WHERE agent_id = ? AND team_id" in sql and params == ["AG-1", "T-1"] else [])
    monkeypatch.setattr(wl, "facts", lambda kind, sid: {"decisions": 0, "overrides": 0})
    assert wl.pin(LEAD, "agent", "AG-1").pinned
    with pytest.raises(HTTPException):
        wl.pin(LEAD, "agent", "AG-2")


def test_what_changed_since_you_last_looked():
    wl.pin(AGENT, "customer", "G-1-MINE")
    item = wl.listing(AGENT).items[0]
    assert item.changes == [] and item.link == "/customers/G-1-MINE" and item.track_link == "/track/customer/G-1-MINE"
    with ops() as con:
        con.execute("INSERT INTO nba_decisions (case_id, golden_id, proposed_json, decision, user_id) VALUES ('C','G-1-MINE','{}','approve','AG-1')")
        con.execute("INSERT INTO hardship_flag_events (golden_id, from_level, to_level, source) VALUES ('G-1-MINE','none','possible','rule')")
    got = wl.listing(AGENT)
    assert got.changed == 1
    assert set(got.items[0].changes) == {"1 new decision on the next best action", "Hardship flag changed from none to possible"}
    wl.mark_seen(AGENT, "customer", "G-1-MINE")
    assert wl.listing(AGENT).items[0].changes == []


def test_a_pin_you_can_no_longer_open_is_shown_as_unavailable(monkeypatch):
    wl.pin(AGENT, "customer", "G-1-MINE")
    monkeypatch.setattr(access, "_count", lambda s, where, param: 0)  # case reassigned
    item = wl.listing(AGENT).items[0]
    assert not item.available and item.changes == [] and "no longer" in item.status


def test_watchlist_table_is_added_to_an_older_ops_db():
    with ops() as con:
        con.execute("DROP TABLE watchlist")
    wl._ready_paths.clear()
    assert wl.pins(AGENT) == []
    assert wl.pin(AGENT, "agent", "AG-1").pinned


def test_http_endpoints(monkeypatch):
    from api.main import app

    c = TestClient(app)
    c.post("/api/auth/session", params={"role": "analyst"})
    assert c.post("/api/watchlist", json={"kind": "customer", "subject_id": "G-1-MINE"}).status_code == 403
    r = c.post("/api/watchlist", json={"kind": "cohort", "subject_id": "product:card", "label": "Cards"})
    assert r.status_code == 200 and r.json()["audit_id"]
    assert c.get("/api/watchlist/pins").json() == [{"kind": "cohort", "subject_id": "product:card"}]
    lst = c.get("/api/watchlist").json()
    assert lst["items"][0]["label"] == "Cards"
    assert c.post("/api/watchlist/cohort/product:card/seen").json()["ok"]
    assert c.delete("/api/watchlist/cohort/product:card").json()["pinned"] is False
    assert c.get("/api/watchlist/pins").json() == []
    assert c.post("/api/watchlist", json={"kind": "planet", "subject_id": "x"}).status_code == 422
