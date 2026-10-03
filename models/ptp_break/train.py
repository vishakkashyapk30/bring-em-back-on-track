"""Train the promise-break model: LightGBM with monotone constraints, isotonic calibration on a later period,
then evaluation against the bank's ptp_break v2.1 on the SAME test promises. Writes the model artefacts and
reports/model_eval.json. Run: python -m models.ptp_break.train"""

from __future__ import annotations

import json
import logging
import pickle
from pathlib import Path

import lightgbm as lgb
import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score

from common.config import get_settings
from models.ptp_break.dataset import CATEGORICAL, FEATURES, NUMERIC, build_dataset

log = logging.getLogger("ptp_break")
ART = Path(__file__).resolve().parent / "artefacts"
# More of these can never LOWER the risk (keeps the model sensible and explainable).
MONOTONE_UP = {"prior_broken_ptp_count", "broken_before_in_case", "dpd_at_creation", "complaints_90d", "disputes_90d"}
LEAK_CHECK_MAX_AUC = 0.90  # a promise-break model this good on real-world-like data means something leaks: stop
FALLBACK = (
    "Promises without a bank v2.1 score are scored by our calibrated model alone and labelled "
    "'our model (no bank v2.1 score)'."
)
PARAMS = dict(
    objective="binary",
    learning_rate=0.05,
    num_leaves=31,
    min_child_samples=100,
    feature_fraction=0.8,
    bagging_fraction=0.8,
    bagging_freq=1,
    lambda_l2=1.0,
    verbose=-1,
    seed=7,
)


def blend_x(v21: np.ndarray, ours_raw: np.ndarray) -> np.ndarray:
    lg = lambda p: np.log(np.clip(p, 1e-4, 1 - 1e-4) / (1 - np.clip(p, 1e-4, 1 - 1e-4)))  # noqa: E731
    return np.c_[lg(np.asarray(v21, dtype=float)), lg(np.asarray(ours_raw, dtype=float))]


def top_decile(y: np.ndarray, p: np.ndarray) -> dict:
    k = max(1, int(len(p) * 0.1))
    idx = np.argsort(-p)[:k]
    prec = float(y[idx].mean())
    return {
        "precision_top10": round(prec, 4),
        "recall_top10": round(float(y[idx].sum() / max(y.sum(), 1)), 4),
        "lift_top10": round(prec / max(float(y.mean()), 1e-9), 3),
    }


def metrics(y: np.ndarray, p: np.ndarray) -> dict:
    return {
        "auc": round(float(roc_auc_score(y, p)), 4),
        "brier": round(float(brier_score_loss(y, p)), 4),
        **top_decile(y, p),
        "n": int(len(y)),
        "base_rate": round(float(y.mean()), 4),
    }


def reliability(y: np.ndarray, p: np.ndarray, bins: int = 10) -> list[dict]:
    edges = np.linspace(0, 1, bins + 1)
    out = []
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        m = (p >= lo) & (p < hi if hi < 1 else p <= hi)
        if m.sum():
            out.append(
                {
                    "bin": f"{lo:.1f}-{hi:.1f}",
                    "predicted": round(float(p[m].mean()), 4),
                    "observed": round(float(y[m].mean()), 4),
                    "n": int(m.sum()),
                }
            )
    return out


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    df = build_dataset()
    tr, ca, te = (df[df.split == s] for s in ("train", "calib", "test"))
    log.info("rows train=%d calib=%d test=%d", len(tr), len(ca), len(te))
    mono = [1 if f in MONOTONE_UP else 0 for f in FEATURES]
    dtr = lgb.Dataset(tr[FEATURES], tr.label_broken, categorical_feature=CATEGORICAL, free_raw_data=False)
    dca = lgb.Dataset(ca[FEATURES], ca.label_broken, categorical_feature=CATEGORICAL, reference=dtr)
    booster = lgb.train(
        {**PARAMS, "monotone_constraints": mono},
        dtr,
        num_boost_round=2000,
        valid_sets=[dca],
        callbacks=[lgb.early_stopping(100, verbose=False)],
    )
    raw_ca = booster.predict(ca[FEATURES], num_iteration=booster.best_iteration)
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.001, y_max=0.999).fit(raw_ca, ca.label_broken)

    raw_te = booster.predict(te[FEATURES], num_iteration=booster.best_iteration)
    p_te = iso.predict(raw_te)
    y_te = te.label_broken.to_numpy()
    both = te.v21_score.notna().to_numpy()

    # Champion/challenger blend: the bank's v2.1 score + our model, two weights fitted on the calibration period
    # (Apr-Jun 2026, where v2.1 exists) and judged on Jul-Sep. Logit inputs; simple and explainable.
    ca_b = ca[ca.v21_score.notna()]
    blender = LogisticRegression().fit(
        blend_x(ca_b.v21_score.to_numpy(), raw_ca[ca.v21_score.notna().to_numpy()]), ca_b.label_broken
    )
    p_blend = blender.predict_proba(blend_x(te.v21_score.to_numpy()[both], raw_te[both]))[:, 1]

    report = {
        "model": "ptp_break ours (LightGBM, monotone, isotonic-calibrated)",
        "split": {
            "train": "created before 2026-04-01",
            "calibration": "Apr-Jun 2026",
            "test": "Jul-Sep 2026",
            "rows": {"train": len(tr), "calibration": len(ca), "test": len(te)},
        },
        "best_iteration": int(booster.best_iteration),
        "test_all": metrics(y_te, p_te),
        "head_to_head": {
            "note": "Same test promises: those the bank's v2.1 also scored.",
            "ours": metrics(y_te[both], p_te[both]),
            "bank_v2_1": metrics(y_te[both], te.v21_score.to_numpy()[both]),
            "blend": metrics(y_te[both], p_blend),
            "blend_weights": {
                "v2_1_logit": round(float(blender.coef_[0][0]), 4),
                "ours_logit": round(float(blender.coef_[0][1]), 4),
                "intercept": round(float(blender.intercept_[0]), 4),
            },
        },
        "calibration_blend": reliability(y_te[both], p_blend),
        "calibration_ours": reliability(y_te[both], p_te[both]),
        "calibration_v2_1": reliability(y_te[both], te.v21_score.to_numpy()[both]),
        "feature_importance_gain": dict(
            sorted(
                zip(FEATURES, (round(float(g), 1) for g in booster.feature_importance("gain")), strict=True),
                key=lambda x: -x[1],
            )[:15]
        ),
        "features": {"numeric": NUMERIC, "categorical": CATEGORICAL, "monotone_increasing": sorted(MONOTONE_UP)},
    }
    h = report["head_to_head"]
    o, b, bl = h["ours"], h["bank_v2_1"], h["blend"]
    better = lambda m: m["auc"] > b["auc"] and m["brier"] <= b["brier"] + 0.005  # noqa: E731
    report["decision"] = (
        "use blend" if better(bl) and bl["auc"] >= o["auc"] else "use ours" if better(o) else "keep bank v2.1"
    )
    log.info(
        "ours AUC %.4f Brier %.4f | v2.1 AUC %.4f Brier %.4f -> %s",
        o["auc"],
        o["brier"],
        b["auc"],
        b["brier"],
        report["decision"],
    )
    if max(o["auc"], bl["auc"]) > LEAK_CHECK_MAX_AUC:
        raise SystemExit(
            f"Test AUC {o['auc']} is implausibly high: check the features for leakage before using this model."
        )

    ART.mkdir(parents=True, exist_ok=True)
    booster.save_model(str(ART / "ptp_break.txt"), num_iteration=booster.best_iteration)
    with open(ART / "calibrator.pkl", "wb") as f:
        pickle.dump(iso, f)
    with open(ART / "blender.pkl", "wb") as f:
        pickle.dump(blender, f)
    cats = {c: list(tr[c].cat.categories) for c in CATEGORICAL}
    (ART / "meta.json").write_text(
        json.dumps(
            {"features": FEATURES, "categorical": CATEGORICAL, "categories": cats, "decision": report["decision"]},
            indent=2,
        )
    )
    report["fallback"] = FALLBACK
    rp = get_settings().reports_dir / "model_eval.json"
    rp.parent.mkdir(parents=True, exist_ok=True)
    rp.write_text(json.dumps(report, indent=2))
    print(json.dumps({k: report[k] for k in ("head_to_head", "decision")}, indent=2))


if __name__ == "__main__":
    main()
