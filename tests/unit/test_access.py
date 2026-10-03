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
    access.case(_specialist(), "CS-1")


def test_nothing_is_enforced_on_sample_data(monkeypatch):
    monkeypatch.setattr(access, "live_data", lambda: False)
    access.case(_agent(), "CS-1")
