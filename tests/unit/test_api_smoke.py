from fastapi.testclient import TestClient

from api.main import app


def test_health_and_login_flow():
    c = TestClient(app)
    assert c.get("/api/health").json()["ok"]
    assert c.get("/api/queue").status_code == 401
    c.post("/api/auth/session", params={"role": "agent"})
    assert c.get("/api/queue").status_code == 200
    assert c.get("/api/hardship/board").status_code == 403  # agent can't see specialist board
    items = c.get("/api/queue").json()["items"]
    case_id = items[0]["case_id"] if items else "CS-1"
    r = c.post(f"/api/nba/{case_id}/decision", json={"decision": "override"})
    assert r.status_code == 422  # override needs a reason code
    r = c.post(f"/api/nba/{case_id}/decision", json={"decision": "approve"})
    assert r.json()["audit_id"] > 0
    assert c.post("/api/nba/CS-NOPE/decision", json={"decision": "approve"}).status_code in (200, 404)


def test_ask_refuses_protected():
    c = TestClient(app)
    c.post("/api/auth/session", params={"role": "analyst"})
    r = c.post("/api/ask", json={"question": "Show cure rate by gender"}).json()
    assert r["refused"]
