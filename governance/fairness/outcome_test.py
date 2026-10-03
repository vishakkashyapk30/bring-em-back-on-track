"""Outcome test by group: does the promise-break score treat protected groups the same way once it meets the
real outcome? Per group (aggregates only, groups with fewer than `suppression_min_group` customers hidden):
break rate, predicted vs observed (calibration gap), share flagged high risk, true and false positive rates, and
how hard past collection effort pushed (attempts in 30 days, contacts in 90 days).

A group goes to "review" when its calibration gap differs from everyone's by more than 3 points (the model
under-predicts breaks overall in the test quarter, so only the excess matters) or its flag rate is outside 0.8x to
1.25x of everyone's. Review means a person looks and explains it (base rates can differ), not an automatic change.
Next-best-action rates by group are added once decisions are produced for the test period (Layer 4).
"""

from __future__ import annotations

import duckdb
import pandas as pd

from common.config import get_settings

FLAG_AT = 0.55  # "high" band and above, the same line the next-best-action rules use
GAP_REVIEW = 0.03
RATIO_REVIEW = (0.8, 1.25)
MIN_PROMISES = 300  # below this a group's rates are too noisy to judge


def _group_row(g: pd.DataFrame, overall_flag: float, overall_gap: float = 0.0) -> dict:
    y, p = g.label_broken.to_numpy(), g.p_break.to_numpy()
    flagged = p >= FLAG_AT
    flag_rate = float(flagged.mean())
    gap = float(p.mean() - y.mean())
    excess = gap - overall_gap
    ratio = flag_rate / overall_flag if overall_flag else None
    status = "ok"
    if len(g) < MIN_PROMISES:
        status = "low volume"
    elif abs(excess) > GAP_REVIEW or (ratio is not None and not RATIO_REVIEW[0] <= ratio <= RATIO_REVIEW[1]):
        status = "review"
    return {
        "promises": int(len(g)),
        "customers": int(g.golden_id.nunique()),
        "break_rate": round(float(y.mean()), 4),
        "predicted": round(float(p.mean()), 4),
        "calibration_gap": round(gap, 4),
        "excess_gap": round(excess, 4),
        "flag_rate": round(flag_rate, 4),
        "flag_ratio": round(ratio, 3) if ratio is not None else None,
        "tpr": round(float(flagged[y == 1].mean()), 4) if (y == 1).any() else None,
        "fpr": round(float(flagged[y == 0].mean()), 4) if (y == 0).any() else None,
        "attempts_30d": round(float(g.attempts_30d.mean()), 2),
        "contacts_90d": round(float(g.contacts_90d.mean()), 2),
        "status": status,
    }


def run() -> dict:
    from governance.fairness import auditor

    s = get_settings()
    scores = pd.read_parquet(s.features_dir / "ptp_test_scores.parquet")
    con = duckdb.connect(str(s.warehouse_path), read_only=True)
    eff = con.sql("SELECT ptp_id, attempts_30d, contacts_90d FROM features.f_ptp_offline").df()
    con.close()
    df = scores.merge(eff, on="ptp_id", how="left").merge(auditor.load(), on="golden_id", how="inner")
    overall_flag = float((df.p_break >= FLAG_AT).mean())
    overall = _group_row(df, overall_flag)
    overall_gap = overall["calibration_gap"]
    out = []
    for attr in auditor.ATTRIBUTES:
        groups, hidden = [], 0
        for val, g in df.groupby(attr, observed=True):
            if g.golden_id.nunique() < s.suppression_min_group:
                hidden += 1
                continue
            groups.append({"group": str(val), **_group_row(g, overall_flag, overall_gap)})
        groups.sort(key=lambda r: -r["promises"])
        n_review = sum(r["status"] == "review" for r in groups)
        out.append({"attribute": attr, "groups": groups, "suppressed_groups": hidden, "reviews": n_review,
                    "worst_gap": max((abs(r["excess_gap"]) for r in groups if r["status"] != "low volume"),
                                     default=0.0)})
    return {"test_period": "Jul to Sep 2026", "promises": int(len(df)), "overall": overall,
            "thresholds": {"flag_at": FLAG_AT, "calibration_gap": GAP_REVIEW, "flag_ratio": list(RATIO_REVIEW),
                           "min_promises": MIN_PROMISES},
            "attributes": out}
