"""Row-level access: agents and team leads open only their own cases, customers and calls."""

import pytest
from fastapi import HTTPException

from api import access
from api.schemas.common import Session


def _agent():
    return Session(user_id="AG-1", role="agent", team_id="T-1", display_name="A")


def _lead():
    return Session(user_id="AG-9", role="team_lead", team_id="T-1", display_name="L")


def _specialist():
    return Session(user_id="AG-5", role="hardship_specialist", team_id="H-1", display_name="S")


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setattr(access, "live_data", lambda: True)


def test_agent_is_refused_a_case_that_is_not_assigned_to_them(live, monkeypatch):
    monkeypatch.setattr(access, "_count", lambda s, where, param: 0)
    for fn, arg in ((access.case, "CS-1"), (access.golden, "G-1"), (access.contact, "CT-1")):
        with pytest.raises(HTTPException) as e:
            fn(_agent(), arg)
        assert e.value.status_code == 403


def test_agent_may_open_their_own(live, monkeypatch):
    monkeypatch.setattr(access, "_count", lambda s, where, param: 1)
    access.case(_agent(), "CS-1")
    access.golden(_agent(), "G-1")
    access.contact(_agent(), "CT-1")


def test_the_query_is_scoped_by_the_agent_or_the_team(live, monkeypatch):
    seen = {}

    class Con:
        def execute(self, sql, params=None):
            seen["sql"], seen["params"] = sql, params
            return self

        def fetchone(self):
            return (1,)

        def close(self):
            pass

    monkeypatch.setattr("common.db.warehouse", lambda *a, **k: Con())
    access.case(_agent(), "CS-1")
    assert "assigned_agent_id" in seen["sql"] and seen["params"] == ["CS-1", "AG-1"]
    access.case(_lead(), "CS-1")
    assert "assigned_team" in seen["sql"] and seen["params"] == ["CS-1", "T-1"]


def test_roles_without_row_scope_are_not_restricted_here(live, monkeypatch):
    monkeypatch.setattr(access, "_count", lambda *a: (_ for _ in ()).throw(AssertionError("no query expected")))
    monkeypatch.setattr(access, "_scoped", lambda s: None)
    access.case(Session(user_id="AN-1", role="analyst"), "CS-1")


def _steward():
    return Session(user_id="DS-1", role="steward", display_name="K")


def test_specialist_query_covers_assigned_flagged_vulnerable_and_board(live, monkeypatch):
    seen = {}

    class Con:
        def execute(self, sql, params=None):
            seen["sql"], seen["params"] = sql, params
            return self

        def fetchone(self):
            return (1,)

        def close(self):
            pass

    monkeypatch.setattr("common.db.warehouse", lambda *a, **k: Con())
    access.case(_specialist(), "CS-1")
    sql = seen["sql"]
    for part in ("assigned_agent_id", "assigned_team", "hardship_flag", "vulnerable_customer_flag", "c360_customer"):
        assert part in sql
    assert seen["params"] == ["CS-1", "AG-5", "H-1"]


def test_specialist_is_refused_a_case_outside_the_rule_before_data_is_read(live, monkeypatch):
    monkeypatch.setattr(access, "_count", lambda s, where, param: 0)
    for fn, arg in ((access.case, "CS-1"), (access.golden, "G-1"), (access.contact, "CT-1")):
        with pytest.raises(HTTPException) as e:
            fn(_specialist(), arg)
        assert e.value.status_code == 403 and "hardship board" in e.value.detail["reason"]


def test_specialist_may_open_a_case_that_matches(live, monkeypatch):
    monkeypatch.setattr(access, "_count", lambda s, where, param: 1)
    access.case(_specialist(), "CS-1")
    access.golden(_specialist(), "G-1")


def test_specialist_flagged_since_the_last_build_is_open_via_the_ops_store(live, monkeypatch):
    class Con:
        n = 0

        def execute(self, sql, params=None):
            return self

        def fetchone(self):
            return (0,)

        def fetchall(self):
            return [("G-9",)]

        def close(self):
            pass

    monkeypatch.setattr("common.db.warehouse", lambda *a, **k: Con())
    monkeypatch.setattr(access, "_flagged_in_ops", lambda gids: gids == ["G-9"])
    access.case(_specialist(), "CS-1")


def test_steward_never_opens_an_individual_customer_case_or_call(live, monkeypatch):
    monkeypatch.setattr(access, "_count", lambda *a: (_ for _ in ()).throw(AssertionError("no query expected")))
    for fn, arg in ((access.case, "CS-1"), (access.golden, "G-1"), (access.contact, "CT-1"), (access.individual, None)):
        with pytest.raises(HTTPException) as e:
            fn(_steward(), arg) if arg else fn(_steward())
        assert e.value.status_code == 403 and "identity lineage" in e.value.detail["reason"]


def test_steward_may_open_identity_lineage_but_others_keep_their_scope(live, monkeypatch):
    monkeypatch.setattr(access, "_count", lambda s, where, param: 0)
    access.lineage(_steward(), "G-1")
    with pytest.raises(HTTPException):
        access.lineage(_agent(), "G-1")


def test_steward_is_refused_the_customer_screens_over_http(monkeypatch):
    from fastapi.testclient import TestClient

    from api.main import app
    from api.personas import DEMO_USERS

    monkeypatch.setattr(access, "live_data", lambda: True)
    monkeypatch.setattr(access, "_count", lambda *a: 1)
    from api.deps import current_session

    app.dependency_overrides[current_session] = lambda: DEMO_USERS["steward"]
    try:
        c = TestClient(app)
        for path in ("/api/customers/G-1", "/api/customers/G-1/timeline"):
            r = c.get(path)
            assert r.status_code == 403 and "identity lineage" in r.json()["detail"]["reason"]
    finally:
        app.dependency_overrides.pop(current_session, None)


def test_nothing_is_enforced_on_sample_data(monkeypatch):
    monkeypatch.setattr(access, "live_data", lambda: False)
    access.case(_agent(), "CS-1")
