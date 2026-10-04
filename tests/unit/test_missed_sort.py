"""H3 missed offers: sort allowlist, direction, default order."""
# ruff: noqa: E501

import pytest
from fastapi.testclient import TestClient

from api.services.hardship import sort_missed

ITEMS = [  # incoming order is newest first
    {"case_id": "A", "dpd": 10, "overdue": 500, "flag_since": "2026-09-20", "eligible_programs": [{"program_name": "Zeta"}]},
    {"case_id": "B", "dpd": 90, "overdue": 100, "flag_since": "2026-09-10", "eligible_programs": [{"program_name": "alpha"}]},
    {"case_id": "C", "dpd": 45, "overdue": 900, "flag_since": "2026-08-01", "eligible_programs": []},
]


def ids(**kw):
    return [i["case_id"] for i in sort_missed(ITEMS, **kw)]


def test_default_is_newest_first_and_unchanged():
    assert ids() == ["A", "B", "C"]
    assert ids(sort="newest", direction="desc") == ["A", "B", "C"]
    assert ids(sort="newest", direction="asc") == ["C", "B", "A"]


def test_each_sort_key():
    assert ids(sort="days_late") == ["B", "C", "A"]
    assert ids(sort="days_late", direction="asc") == ["A", "C", "B"]
    assert ids(sort="exposure") == ["C", "A", "B"]
    assert ids(sort="days_since_flag") == ["C", "B", "A"]  # oldest flag has most days
    assert ids(sort="days_since_flag", direction="asc") == ["A", "B", "C"]
    assert ids(sort="program") == ["B", "A", "C"]  # a to z, case-insensitive, none last
    assert ids(sort="program", direction="desc") == ["C", "A", "B"]


def test_input_not_mutated():
    before = [i["case_id"] for i in ITEMS]
    sort_missed(ITEMS, "exposure", "asc")
    assert [i["case_id"] for i in ITEMS] == before


@pytest.mark.parametrize("sort,d", [("dpd; DROP TABLE x", None), ("overdue", None), ("newest", "sideways")])
def test_rejects_values_outside_allowlist(sort, d):
    with pytest.raises(ValueError):
        sort_missed(ITEMS, sort, d)


def _specialist_client(monkeypatch):
    from api.main import app
    from api.routers import hardship

    monkeypatch.setattr(hardship, "live_data", lambda: False)
    c = TestClient(app)
    c.post("/api/auth/session", params={"role": "hardship_specialist"})
    return c


def test_route_default_and_allowlist(monkeypatch):
    c = _specialist_client(monkeypatch)
    assert c.get("/api/hardship/missed-offers").status_code == 200
    ok = c.get("/api/hardship/missed-offers", params={"sort": "exposure", "dir": "asc"})
    assert ok.status_code == 200
    for bad in ({"sort": "1; DROP TABLE x"}, {"sort": "overdue"}, {"dir": "up"}):
        assert c.get("/api/hardship/missed-offers", params=bad).status_code == 422


def test_route_default_order_is_service_order(monkeypatch):
    from api.routers import hardship

    c = _specialist_client(monkeypatch)
    monkeypatch.setattr(hardship, "live_data", lambda: True)
    seen = {}
    monkeypatch.setattr(hardship.hardship_svc, "missed_offers", lambda **kw: seen.update(kw) or {"items": []})
    c.get("/api/hardship/missed-offers")
    assert seen == {"sort": "newest", "direction": None}
