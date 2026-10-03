import datetime as dt
import json

import pytest
from fastapi.testclient import TestClient

from common.db import ops
from decisioning import outage_shield, playbooks
from governance import audit

WEEK = dt.date(2026, 9, 28)


def row(pattern="layoff_like", behind=("G1", "G2"), not_behind=("G3",), incident=None):
    return {"employer_key": "EMP-X", "week_start": "2026-09-28", "pattern": pattern, "n_customers": 12,
            "n_payroll_gap": 9, "n_new_ei": 7, "explained_by_incident": incident, "label": "L",
            "members_behind": list(behind), "members_not_behind": list(not_behind),
            "members": list(behind) + list(not_behind)}


def test_layoff_like_proposes_hold_and_contact_with_signoff():
    ps = playbooks.from_radar([row()])
    kinds = {p["kind"]: p for p in ps}
    assert set(kinds) == {"hold", "contact"}
    assert kinds["contact"]["requires_policy_office_signoff"] is True
    assert kinds["hold"].get("requires_policy_office_signoff", False) is False


def test_payroll_delay_and_known_incident_only_hold():
    assert [p["kind"] for p in playbooks.from_radar([row("payroll_delay")])] == ["hold"]
    assert [p["kind"] for p in playbooks.from_radar([row(incident="INC-1")])] == ["hold"]
    assert playbooks.from_radar([row("none")]) == []


def test_proposals_are_pending_and_approval_creates_a_batch_not_a_contact():
    playbooks.store(playbooks.from_radar([row()]))
    assert all(p["status"] == "pending_approval" for p in playbooks.listing())
    hold = next(p for p in playbooks.listing() if p["kind"] == "hold")
    res = playbooks.approve(hold["proposal_id"], "AG-9", "team_lead", "T-1", today=WEEK)
    assert res["batch_status"] == "pending" and res["sample_size"] == 1
    with ops() as con:
        b = con.execute("SELECT * FROM batches WHERE batch_id = ?", (res["batch_id"],)).fetchone()
    assert b["kind"] == "radar_playbook" and json.loads(b["items_json"]) == ["G1", "G2"]
    assert audit.query(event_type="playbook_approve")[0]["entity_id"] == hold["proposal_id"]
    with pytest.raises(ValueError):
        playbooks.approve(hold["proposal_id"], "AG-9", "team_lead")


def test_contact_batch_waits_for_the_policy_office():
    playbooks.store(playbooks.from_radar([row()]))
    c = next(p for p in playbooks.listing() if p["kind"] == "contact")
    assert playbooks.approve(c["proposal_id"], "AG-9", "team_lead")["batch_status"] == "awaiting_policy_office"


@pytest.mark.parametrize("role", ["agent", "hardship_specialist", "analyst", "steward", "data_steward"])
def test_only_a_team_lead_approves(role):
    playbooks.store(playbooks.from_radar([row()]))
    with pytest.raises(PermissionError):
        playbooks.approve(playbooks.listing()[0]["proposal_id"], "u", role)


def test_reject_needs_a_reason():
    playbooks.store(playbooks.from_radar([row()]))
    pid = playbooks.listing()[0]["proposal_id"]
    with pytest.raises(ValueError):
        playbooks.reject(pid, "u", "team_lead", " ")
    assert playbooks.reject(pid, "u", "team_lead", "not now")["status"] == "rejected"


def test_regional_playbook_hides_small_areas():
    areas = [{"area": f"A{i}", "n_customers": 50, "broken_promise_rate": 0.1} for i in range(5)]
    areas += [{"area": "HOT", "n_customers": 40, "broken_promise_rate": 0.5},
              {"area": "TINY", "n_customers": 5, "broken_promise_rate": 0.9}]
    ps = playbooks.from_areas(areas)
    assert {p["subject_id"] for p in ps} == {"HOT"} and {p["kind"] for p in ps} == {"hold", "contact"}


def test_outage_victims_get_fee_reversal_and_pressure_hold():
    ev = {"event_id": "INC-0914", "event_type": "app_outage", "start_ts": dt.datetime(2026, 9, 14, 9),
          "end_ts": dt.datetime(2026, 9, 14, 15), "description": "Payments not posted until next day",
          "affected_customers_est": 1900}
    d = dt.date(2026, 9, 14)
    reps = [{"account_id": "A1", "golden_id": "G1", "due_date": d, "paid_date": d + dt.timedelta(days=1),
             "fees_charged": 25.0, "fees_reversed": 0.0},
            {"account_id": "A2", "golden_id": "G2", "due_date": d, "paid_date": d + dt.timedelta(days=9)}]
    assert outage_shield.is_payment_outage(ev)
    rep = outage_shield.victims(ev, reps)
    assert rep["candidates"] == ["A1"] and rep["bank_estimate"] == 1900 and rep["is_candidate_list"]
    assert {p["kind"] for p in rep["proposals"]} == {"fee_reversal", "pressure_hold"}
    playbooks.store(playbooks.from_outage(rep))
    assert all(p["status"] == "pending_approval" for p in playbooks.listing())
    dialer = {"event_id": "INC-0923", "event_type": "dialer_outage", "affected_tables": '["contact_history"]',
              "description": "Outbound dialer degraded"}
    assert not outage_shield.is_payment_outage(dialer)


def test_api_roles_and_flow(monkeypatch):
    from api.main import app

    monkeypatch.setattr("api.routers.playbooks.live_data", lambda: False)
    playbooks.store(playbooks.from_radar([row()]))
    c = TestClient(app)
    assert c.get("/api/playbooks").status_code == 401
    c.post("/api/auth/session", params={"role": "analyst"})
    assert c.get("/api/playbooks").status_code == 403
    r = c.get("/api/radar").json()
    assert r["rows"] == [] and r["clusters"] == 0
    c.post("/api/auth/session", params={"role": "agent"})
    assert c.get("/api/radar").status_code == 403
    c.post("/api/auth/session", params={"role": "team_lead"})
    items = c.get("/api/playbooks").json()["items"]
    assert items and c.post(f"/api/playbooks/{items[0]['proposal_id']}/approve").json()["audit_id"] > 0
    assert c.get("/api/drift").status_code == 403


def test_api_drift_only_steward_approves(monkeypatch):
    from api.main import app
    from governance import drift

    monkeypatch.setattr("api.routers.drift.live_data", lambda: False)
    fix = drift.record(drift.detect("contact_history", [{"channel": "a"}], [{"channel_v2": "a"}]))
    c = TestClient(app)
    c.post("/api/auth/session", params={"role": "team_lead"})
    assert c.post(f"/api/drift/{fix['fix_id']}/approve").status_code == 403
    c.post("/api/auth/session", params={"role": "steward"})
    assert c.get("/api/drift").json()["pending"] == 1
    r = c.post(f"/api/drift/{fix['fix_id']}/approve").json()
    assert r["applied"] is False and r["status"] == "approved_by_engineer"
    assert c.post(f"/api/drift/{fix['fix_id']}/approve").status_code == 409
