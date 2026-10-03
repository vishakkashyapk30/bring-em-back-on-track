from pathlib import Path

import pandas as pd

from governance.fairness import outcome_test
from governance.fairness.proxy_test import group_proxy_auc

ROOT = Path(__file__).resolve().parents[2]


def test_only_the_fairness_package_reads_the_protected_table():
    offenders = []
    for p in ROOT.rglob("*.py"):
        parts = p.relative_to(ROOT).parts
        skip = {".venv", "node_modules", "tests", "tests_spec", "web"}
        if parts[0] in skip or parts[:2] == ("governance", "fairness"):
            continue
        if "stg_customers_protected" in p.read_text(errors="ignore"):
            offenders.append(str(p.relative_to(ROOT)))
    assert offenders == []


def _frame(n=1000, gap=0.0, flag_p=0.7):
    # first half "broken" with prediction flag_p, second half "kept" with the same prediction
    y = [1] * (n // 2) + [0] * (n // 2)
    return pd.DataFrame({"golden_id": [f"G-{i}" for i in range(n)], "label_broken": y,
                         "p_break": [flag_p + gap] * n, "attempts_30d": 3.0, "contacts_90d": 7.0})


def test_group_with_the_same_gap_and_flag_rate_is_ok():
    row = outcome_test._group_row(_frame(), overall_flag=1.0, overall_gap=0.2)
    assert row["status"] == "ok" and row["flag_ratio"] == 1.0


def test_group_flagged_far_more_often_goes_to_review():
    row = outcome_test._group_row(_frame(), overall_flag=0.5, overall_gap=0.2)
    assert row["status"] == "review"


def test_small_group_is_marked_low_volume_not_judged():
    row = outcome_test._group_row(_frame(n=100), overall_flag=0.5, overall_gap=0.2)
    assert row["status"] == "low volume"


def test_proxy_test_flags_a_group_that_copies_a_protected_attribute():
    feats = [{"entity_id": i, "copy": float(i % 2), "noise": float((i * 7919) % 13)} for i in range(400)]
    prot = [{"entity_id": i, "gender_code": "F" if i % 2 else "M"} for i in range(400)]
    res = group_proxy_auc(feats, prot, {"proxy": ["copy"], "other": ["noise"]})
    assert res["proxy"]["decision"] == "review" and res["other"]["decision"] == "keep"
