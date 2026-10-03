import datetime as dt

from decisioning import radar

WEEK = dt.date(2026, 9, 28)


def obs(key, n, gaps, ei, industry="33", open_every=2):
    return [radar.Observation(f"G-{key}-{i}", key, industry, WEEK, i < gaps, i < ei, has_open_case=i % open_every == 0,
                              exposure_cad=100.0) for i in range(n)]


def test_layoff_like_payroll_delay_and_none():
    rows = radar.compute(obs("A", 12, 9, 7) + obs("B", 12, 10, 0) + obs("C", 12, 0, 0))
    by = {r["employer_key"]: r for r in rows}
    assert by["A"]["pattern"] == "layoff_like" and by["B"]["pattern"] == "payroll_delay"
    assert by["C"]["pattern"] == "none"


def test_small_groups_never_leave_the_function():
    rows = radar.compute(obs("BIG", 12, 8, 6) + obs("SMALL", 9, 9, 9))
    assert {r["employer_key"] for r in rows} == {"BIG"}
    assert all("SMALL" not in str(r) for r in rows)


def test_known_incident_is_marked_and_label_is_honest():
    ev = {"event_id": "INC-1", "event_type": "data_feed_issue", "affected_tables": ["deposit_accounts"],
          "start_ts": dt.datetime(2026, 9, 27), "end_ts": dt.datetime(2026, 10, 3), "description": "late file"}
    r = radar.compute(obs("B", 12, 10, 0), [ev])[0]
    assert r["explained_by_incident"] == "INC-1"
    assert "not a layoff detector" in r["label"].lower() and "laid off" not in r["label"].lower()


def test_open_cases_and_exposure_and_own_history():
    later = [radar.Observation(o.golden_id, o.employer_key, o.industry_naics2, WEEK + dt.timedelta(days=7),
                               o.payroll_gap, o.new_ei_deposit, -0.2, o.has_open_case, o.exposure_cad)
             for o in obs("A", 12, 9, 7)]
    first = obs("A", 12, 0, 0)
    rows = radar.compute(first + later)
    r = next(x for x in rows if x["week_start"] == "2026-10-05")
    assert r["open_cases"] == 6 and r["exposure_cad"] == 600.0
    assert r["own_history_change_pct"] == 0.0 and r["avg_payroll_change_pct"] == -0.2


def test_many_employers_do_not_create_false_alarms():
    groups = []
    for k in range(300):  # 300 employers each with 24 customers, 1 or 2 late: pure noise around 6%
        groups += obs(f"E{k}", 24, 1 + (k % 4 == 0) + 4 * (k == 7), 0)
    flagged = [r for r in radar.compute(groups) if r["pattern"] != "none"]
    assert flagged == []


def test_a_real_cluster_among_many_employers_is_found():
    groups = []
    for k in range(100):
        groups += obs(f"E{k}", 24, 1, 0)
    groups += obs("HIT", 24, 18, 12)
    flagged = [r["employer_key"] for r in radar.compute(groups) if r["pattern"] != "none"]
    assert flagged == ["HIT"]


def test_employer_token_hides_the_name():
    assert radar.employer_token("Lakeshore Auto Parts Ltd.").startswith("EMP-")
    assert "lakeshore" not in radar.employer_token("Lakeshore Auto Parts Ltd.").lower()
