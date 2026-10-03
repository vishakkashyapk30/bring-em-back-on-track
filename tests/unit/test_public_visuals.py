"""Public landing visuals: payload shapes, small-group suppression and no identifying fields."""

import json
from datetime import date

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.services import public_visuals as pv
from common.config import get_settings

live = pytest.mark.skipif(not get_settings().warehouse_path.exists(), reason="warehouse not built")


def test_month_list_is_twelve_months_ending_at_as_of():
    m = pv.month_list(date(2026, 2, 10))
    assert len(m) == 12 and m[0] == "2025-03" and m[-1] == "2026-02"


def test_aggregate_hides_small_groups_and_computes_rate():
    rows = [("ON", "2026-01", f"G{i}", int(i < 5), "no_funds" if i < 5 else None) for i in range(20)]
    rows += [("NU", "2026-01", f"N{i}", 1, "forgot") for i in range(4)]  # 4 customers: under the limit
    df = pd.DataFrame(rows, columns=["pr", "m", "golden_id", "v", "reason"])
    series, national = pv.aggregate(df, ["2026-01", "2026-02"], True, 10)
    assert series["ON"]["value"] == [25.0, None]
    assert series["NU"]["value"] == [None, None] and series["NU"]["n"] == [None, None]
    assert series["ON"]["n"][0] == 20 and series["ON"]["top"][0] == "Not enough money"
    assert national[1] is None


def test_aggregate_per_thousand_snapshot():
    ids = [f"G{i}" for i in range(12)]
    df = pd.DataFrame({"pr": ["ON"] * 12, "golden_id": ids, "v": 1, "reason": "missed_payment"})
    series, national = pv.aggregate(df, ["2026-01"], False, 10, {"pr": {"ON": 1000}, "all": 2000})
    assert series["ON"]["value"] == [12.0] and national == [6.0]


@live
def test_endpoints_shapes_and_privacy():
    c = TestClient(app)
    c.post("/api/auth/session", params={"role": "analyst"})
    m = c.get("/api/public/map").json()
    assert len(m["months"]) == 12 and set(m["metrics"]) >= {"broken_ptp_rate", "hardship_rate", "open_cases"}
    for met in m["metrics"].values():
        assert all(i["n"] >= m["min_group"] for i in met["fsas"])
        for s in met["series"].values():
            assert all(n is None or n >= m["min_group"] for n in s["n"])
    f = c.get("/api/public/flow").json()
    if f["available"]:
        ids = {n["id"] for n in f["nodes"]}
        assert all(link["source"] in ids and link["target"] in ids for link in f["links"])
        assert next(n for n in f["nodes"] if n["id"] == "cases")["value"] == f["total"]
    s = c.get("/api/public/sample-customer").json()
    blob = json.dumps(s)
    assert "G-" not in blob and "CS-" not in blob
    assert all(set(r) == {"system", "label", "method", "confidence"} for r in s["records"])


def test_nothing_data_driven_is_served_before_sign_in():
    c = TestClient(app)
    for path in ("summary", "map", "flow", "sample-customer"):
        assert c.get(f"/api/public/{path}").status_code == 401, path
