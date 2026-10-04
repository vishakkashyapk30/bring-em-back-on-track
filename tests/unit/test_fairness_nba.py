import pandas as pd

from governance.fairness import nba_rates as nr


def _queue(rows):
    base = {"hardship_flag": "none", "vulnerable": False, "route_to": None, "status": "scheduled", "p_break": 0.5,
            "priority": 10.0, "plan_date": "2026-09-28"}
    return pd.DataFrame([{**base, "case_id": f"C{i}", "golden_id": f"G{i}", **r} for i, r in enumerate(rows)])


def _prot(n_a, n_b):
    return pd.DataFrame({"golden_id": [f"G{i}" for i in range(n_a + n_b)], "grp": ["a"] * n_a + ["b"] * n_b})


def test_flags_group_outside_ratio_and_ignores_small_groups():
    rows = [{"treatment": "payment_link"} for _ in range(40)] + [{"treatment": "no_contact"} for _ in range(160)]
    rows += [{"treatment": "no_contact"} for _ in range(60)] + [{"treatment": "payment_link"} for _ in range(40)]
    # group a: 200 cases, 20% pressure; group b: 100 cases, 40% pressure
    q = _queue(rows[:40] + rows[40:200] + rows[200:])
    res = nr.by_group(q, _prot(200, 100), ["grp"], min_group=50, suppression_min=10)
    g = {r["group"]: r for r in res["attributes"][0]["groups"]}
    assert g["b"]["status"] == "review" and "pressure_rate" in g["b"]["flags"]
    small = nr.by_group(q, _prot(200, 100), ["grp"], min_group=150, suppression_min=10)
    assert {r["group"]: r["status"] for r in small["attributes"][0]["groups"]}["b"] == "low volume"
    assert abs(g["a"]["mix"]["payment_link"] - 0.2) < 1e-9


def test_suppresses_tiny_groups():
    q = _queue([{"treatment": "reminder"}] * 30)
    res = nr.by_group(q, _prot(25, 5), ["grp"], min_group=1, suppression_min=10)
    assert res["attributes"][0]["suppressed_groups"] == 1
    assert [r["group"] for r in res["attributes"][0]["groups"]] == ["a"]


def test_design_claim_holds_and_detects_violation():
    ok = _queue([{"treatment": "specialist_referral", "vulnerable": True, "route_to": "person"},
                 {"treatment": "payment_link"}])
    assert nr.risk_never_raised_pressure(ok)["violations"] == 0
    bad = _queue([{"treatment": "reminder", "hardship_flag": "clear"}])
    assert nr.risk_never_raised_pressure(bad)["violations"] == 1


def test_counterfactual_counts_only_risk_driven_pressure():
    q = _queue([{"treatment": "no_contact", "vulnerable": True}, {"treatment": "no_contact", "vulnerable": True}])
    flat = nr.risk_never_raised_pressure(q, lambda cid, p: "specialist_referral")
    assert flat["counterfactual_checked"] == 2 and flat["violations"] == 0
    raised = nr.risk_never_raised_pressure(q, lambda cid, p: "reminder" if p > 0.5 else "no_contact")
    assert raised["counterfactual_violations"] == 2 and not raised["holds"]
