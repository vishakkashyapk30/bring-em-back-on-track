"""Small-group suppression: hide any group smaller than 10 (V1 §4, §10; NI S1, S2)."""

from __future__ import annotations

import pytest

from tests_spec import factories as F
from tests_spec import spec_constants as C

pytestmark = pytest.mark.governance


@pytest.mark.parametrize("n,kept", [(0, False), (1, False), (9, False), (10, True), (11, True), (250, True)])
def test_groups_below_ten_are_suppressed(adapter, n, kept):
    """V1 §10 Access: "Employer and map views hide any group smaller than 10"; V1 §4 S2 "hides any area
    with fewer than 10 customers"."""
    rows = [{"group": "A", "n_customers": n, "broken_rate": 0.4}]
    out = adapter.suppress_small_groups(rows, "n_customers")
    visible = [r for r in out if r.get("group") == "A" and r.get("broken_rate") is not None]
    assert bool(visible) is kept


def test_suppression_leaves_large_groups_untouched(adapter):
    """V1 §10: only groups under 10 are hidden; the rest are shown as they are."""
    rows = [{"group": "big", "n_customers": 40, "broken_rate": 0.25}, {"group": "tiny", "n_customers": 3, "broken_rate": 1.0}]
    out = adapter.suppress_small_groups(rows, "n_customers")
    big = [r for r in out if r.get("group") == "big"]
    assert big and big[0]["broken_rate"] == pytest.approx(0.25)
    assert not any(r.get("group") == "tiny" and r.get("broken_rate") is not None for r in out)


@pytest.mark.s2
def test_weather_map_hides_small_areas(adapter):
    """V1 §4 Analyst views (S2): the map "hides any area with fewer than 10 customers"; NI S2."""
    obs = F.area_observations("N9A", 25, 10) + F.area_observations("K0K", 4, 4)
    res = adapter.weather_map(obs)
    areas = {b.area for b in res.bubbles}
    assert "N9A" in areas and "K0K" not in areas
    assert all(b.n_customers >= C.SMALL_GROUP_MIN_SIZE for b in res.bubbles)


@pytest.mark.s2
def test_weather_map_shows_its_sql(adapter):
    """NI S2: "Served through Ask, so every chart shows its SQL"."""
    res = adapter.weather_map(F.area_observations("N9A", 25, 10))
    assert res.sql and "select" in res.sql.lower()


@pytest.mark.s1
def test_employer_radar_hides_employers_under_ten(adapter):
    """V1 §6 Team-lead playbooks: "Only employers with 10 or more customers are shown"; NI S1 step 3."""
    obs = F.employer_observations("EMP-BIG", 12, gaps=8, new_ei=6) + F.employer_observations("EMP-SMALL", 9, gaps=9, new_ei=9)
    rows = adapter.employer_radar(obs)
    keys = {r.employer_key for r in rows}
    assert "EMP-SMALL" not in keys
    assert all(r.n_customers >= C.SMALL_GROUP_MIN_SIZE for r in rows)
