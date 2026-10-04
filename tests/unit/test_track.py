# ruff: noqa: E501
"""Track: authorisation per role (before any data is read), analysts get aggregates only, agents cannot track another
agent's customer, and the analyst's only write (a strategy-test proposal) is audited and approved by a team lead."""

import json
import re

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api import access
from api.schemas.common import Session
from api.services import track
from decisioning import playbooks
from governance import audit

AGENT = Session(user_id="AG-1", role="agent", team_id="T-1")
LEAD = Session(user_id="AG-9", role="team_lead", team_id="T-1")
SPECIALIST = Session(user_id="AG-5", role="hardship_specialist", team_id="H-1")
ANALYST = Session(user_id="AN-1", role="analyst")
STEWARD = Session(user_id="DS-1", role="steward")


@pytest.fixture
def no_warehouse(monkeypatch):
    """Any warehouse read fails the test: authorisation must decide first."""
    def boom(*a, **k):
        raise AssertionError("the warehouse was read before authorisation")

    monkeypatch.setattr(track, "warehouse", boom)
    monkeypatch.setattr("common.db.warehouse", boom)


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setattr(access, "live_data", lambda: True)


@pytest.mark.parametrize("session,kind", [
    (AGENT, "cohort"), (AGENT, "agent"), (AGENT, "identity"), (AGENT, "product"), (AGENT, "employer"),
    (SPECIALIST, "cohort"), (SPECIALIST, "agent"),
    (LEAD, "customer"), (LEAD, "cohort"), (LEAD, "identity"),
    (ANALYST, "customer"), (ANALYST, "agent"), (ANALYST, "employer"), (ANALYST, "identity"),
    (STEWARD, "customer"), (STEWARD, "agent"), (STEWARD, "cohort"),
])
def test_each_role_tracks_only_its_own_kinds(no_warehouse, session, kind):
    with pytest.raises(HTTPException) as e:
        track.authorize(session, kind, "G-ABC1234")
    assert e.value.status_code == 403
    with pytest.raises(HTTPException):
        track.subjects(session, kind, "")


def test_kinds_per_role():
    assert track.kinds_for(AGENT) == ["customer"]
    assert track.kinds_for(SPECIALIST) == ["customer"]
    assert track.kinds_for(LEAD) == ["agent", "employer"]
    assert track.kinds_for(ANALYST) == ["cohort"]
    assert track.kinds_for(STEWARD) == ["identity", "product"]


def test_agent_cannot_track_another_agents_customer(live, no_warehouse, monkeypatch):
    monkeypatch.setattr(access, "_count", lambda s, where, param: 0)  # no case of this customer is assigned to AG-1
    monkeypatch.setattr(track, "_customer_records", lambda *a: (_ for _ in ()).throw(AssertionError("data read")))
    with pytest.raises(HTTPException) as e:
        track.view(AGENT, "customer", "G-ABC1234")
    assert e.value.status_code == 403
    assert "not assigned to you" in e.value.detail["reason"]


def test_agent_may_track_their_own_customer(live, monkeypatch):
    seen = {}
    monkeypatch.setattr(access, "_count", lambda s, where, param: seen.setdefault("args", (s.user_id, param)) and 1)
    track.authorize(AGENT, "customer", "G-ABC1234")
    assert seen["args"] == ("AG-1", "G-ABC1234")


def test_specialist_follows_the_hardship_row_rule(live, no_warehouse, monkeypatch):
    monkeypatch.setattr(access, "_count", lambda s, where, param: 0)
    with pytest.raises(HTTPException) as e:
        track.authorize(SPECIALIST, "customer", "G-ABC1234")
    assert e.value.detail["reason"] == access.SPECIALIST_DENIED


def test_steward_tracks_identity_lineage_but_never_a_customer_record(live, no_warehouse):
    track.authorize(STEWARD, "identity", "G-ABC1234")  # lineage is open to stewards
    with pytest.raises(HTTPException) as e:
        track.authorize(STEWARD, "customer", "G-ABC1234")
    assert e.value.status_code == 403


def test_team_lead_only_tracks_agents_on_their_team(monkeypatch):
    monkeypatch.setattr(track, "_agent_on_team", lambda s, a: a == "AG-2002")
    track.authorize(LEAD, "agent", "AG-2002")
    with pytest.raises(HTTPException) as e:
        track.authorize(LEAD, "agent", "AG-3003")
    assert e.value.detail["reason"] == "This agent is not on your team."


def test_small_employers_are_hidden(monkeypatch):
    monkeypatch.setattr(track, "_employer_size", lambda k: 9)
    with pytest.raises(HTTPException) as e:
        track.authorize(LEAD, "employer", "EMP-0123ABCD")
    assert "fewer than 10" in e.value.detail["reason"]
    monkeypatch.setattr(track, "_employer_size", lambda k: 10)
    track.authorize(LEAD, "employer", "EMP-0123ABCD")


@pytest.mark.parametrize("bad", ["province:ON' OR 1=1 --", "month:2026-13", "week:2026-09-15", "fsa:n9a; drop", "product:boats",
                                 "strategy:early; select", "nothing"])
def test_cohort_ids_are_validated_before_sql(no_warehouse, bad):
    with pytest.raises(HTTPException) as e:
        track.parse_cohort(bad)
    assert e.value.status_code == 422


def test_cohort_ids_compile_to_a_closed_predicate():
    assert track.parse_cohort("month:2026-06")["where"] == "c.case_open_date >= DATE '2026-06-01' AND c.case_open_date < DATE '2026-07-01'"
    assert track.parse_cohort("week:2026-09-14")["where"].endswith("DATE '2026-09-21'")
    assert track.parse_cohort("province:ON")["where"] == "c.province_code = 'ON'"


class FakeW:
    """Answers the analyst cohort queries with aggregates (and one group under 10 that must be hidden)."""

    def __init__(self, customers=480):
        self.customers = customers
        self.sql: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def q(self, sql, params=None):
        self.sql.append(sql)
        if "AS customers FROM collections_cases c LEFT JOIN identity.case_xref" in sql:
            return [{"cases": 500, "customers": self.customers}]
        if "AS driver" in sql:
            return [{"driver": "primary_product", "grp": "card", "cure_rate_pct": 55.0, "cases": 300, "cured_any_time_pct": 70.0},
                    {"driver": "primary_product", "grp": "mortgage", "cure_rate_pct": 20.0, "cases": 120, "cured_any_time_pct": 30.0},
                    {"driver": "primary_product", "grp": "auto_loan", "cure_rate_pct": 100.0, "cases": 3, "cured_any_time_pct": 100.0}]
        if "cure_d7" in sql:
            out = {}
            for d in track.CURVE_DAYS:
                out.update({f"cure_d{d}": 10.0 + d / 3, f"n_cure_d{d}": 400 if d < 90 else 6, f"roll_d{d}": 20.0, f"n_roll_d{d}": 400})
            return [out]
        if "SELECT strategy_code FROM collections_cases" in sql or "SELECT DISTINCT strategy_code" in sql:
            return [{"strategy_code": "MID-CALL-HEAVY"}, {"strategy_code": "EARLY-SMS-ONLY"}]
        if "promise_kept_rate_pct" in sql:
            return [{"month": "2026-06", "promise_kept_rate_pct": 40.0, "promises": 200}, {"month": "2026-07", "promise_kept_rate_pct": 50.0, "promises": 4}]
        if "AS month" in sql:
            return [{"month": "2026-05", "cure_rate_pct": 45.0, "cases": 250, "cured_any_time_pct": 60.0}]
        return [{"cure_rate_pct": 41.0, "cases": 450, "cured_any_time_pct": 60.0}]


def test_analyst_cohort_is_aggregates_only_with_suppression(monkeypatch):
    fake = FakeW()
    monkeypatch.setattr(track, "_W", lambda: fake)
    v = track.view(ANALYST, "cohort", "province:ON")
    assert v.aggregates_only and v.golden_id is None and v.case_id is None
    blob = json.dumps(v.model_dump())
    assert not re.search(r"\bG-[A-Z0-9]{4,}", blob), "a golden ID leaked into an analyst view"
    assert not re.search(r"\bCS-\d{4}-\d+", blob), "a case ID leaked into an analyst view"
    assert not re.search(r"\b(PTP|CT|AG)-\d+", blob)
    assert all(s.kind != "timeline" for s in v.sections)  # no record-level events for analysts
    drivers = next(s for s in v.sections if s.id == "drivers").tables[0]
    assert [r[1] for r in drivers.rows] == ["card", "mortgage"]  # the 3-case group is hidden
    curve = next(s for s in v.sections if s.id == "curves").series[0]
    assert curve.lines[0].values[-1] is None  # day 90 had 6 cases: hidden
    kept = next(s for s in v.sections if s.id == "monthly").series[1]
    assert kept.lines[0].values[-3] is None  # July had 4 promises: hidden
    for ins in v.insights:
        assert ins.reason and ins.source.label and (ins.source.sql or ins.source.ids or ins.source.kind != "sql")
    assert any("collections_cases c" in (i.source.sql or "") for i in v.insights)  # the certified SQL is shown


def test_analyst_cohort_under_10_customers_is_refused(monkeypatch):
    monkeypatch.setattr(track, "_W", lambda: FakeW(customers=7))
    with pytest.raises(HTTPException) as e:
        track.view(ANALYST, "cohort", "province:PE")
    assert "fewer than 10" in e.value.detail["reason"]


def test_propose_test_is_audited_and_a_team_lead_approves_without_a_batch(monkeypatch):
    monkeypatch.setattr(track, "_W", lambda: FakeW())
    res = track.propose_test(ANALYST, "province:ON", "MID-CALL-HEAVY", "try calls first")
    p = playbooks.get(res.proposal_id)
    assert p["status"] == playbooks.PENDING and p["playbook"] == "strategy_test" and p["subject_id"] == "province:ON"
    row = audit.query(limit=5, event_type="strategy_test_propose")[0]
    assert row["entity_id"] == res.proposal_id and row["user_id"] == "AN-1" and row["audit_id"] == res.audit_id
    with pytest.raises(HTTPException) as e:
        track.propose_test(ANALYST, "province:ON", "MID-CALL-HEAVY", None)
    assert e.value.status_code == 409
    with pytest.raises(HTTPException):
        track.propose_test(ANALYST, "province:ON", "NOT-A-STRATEGY", None)
    with pytest.raises(PermissionError):
        playbooks.approve(res.proposal_id, "AN-1", "analyst")  # read-only to the analyst
    out = playbooks.approve(res.proposal_id, "AG-9", "team_lead", "T-1")
    assert out["status"] == "approved" and out["batch_id"] == ""
    from common.db import ops

    with ops() as con:
        assert con.execute("SELECT count(*) FROM batches").fetchone()[0] == 0  # nothing to send, nobody contacted


def test_only_analysts_may_propose(monkeypatch):
    with pytest.raises(HTTPException):
        track.propose_test(LEAD, "province:ON", "MID-CALL-HEAVY", None)


def test_router_refuses_wrong_kind_before_reading_anything(no_warehouse):
    from api.main import app

    c = TestClient(app)
    c.post("/api/auth/session", params={"role": "agent"})
    r = c.get("/api/track/cohort/month:2026-06")
    assert r.status_code == 403 and "not available for the agent role" in r.json()["detail"]["reason"]
    assert c.get("/api/track/subjects", params={"kind": "agent"}).status_code == 403
    assert c.post("/api/track/cohort/month:2026-06/propose", json={"strategy_code": "MID-CALL-HEAVY"}).status_code == 403
