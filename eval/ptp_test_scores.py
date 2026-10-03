"""Score the held-out test promises (Jul-Sep 2026) with the chosen promise-break model, for the fairness audit.

The audit needs, for every test promise, the score the live system would have used and the real outcome. This
writes `data/features/ptp_test_scores.parquet` (ptp_id, golden_id, ptp_created_ts, label_broken, p_break, model).
It contains no protected attributes: the fairness package joins those itself, through the restricted view.
Run: python -m eval.ptp_test_scores
"""

from __future__ import annotations

import json
import pickle

import lightgbm as lgb
import numpy as np
import pandas as pd

from common.config import get_settings
from models.ptp_break.dataset import FEATURES, build_dataset
from models.ptp_break.train import ART, blend_x


def main() -> pd.DataFrame:
    s = get_settings()
    meta = json.loads((ART / "meta.json").read_text())
    decision = meta["decision"]
    df = build_dataset()
    df = df[df.split == "test"].copy()
    for c, cats in meta["categories"].items():
        df[c] = pd.Categorical(df[c].astype(str), categories=cats)
    booster = lgb.Booster(model_file=str(ART / "ptp_break.txt"))
    raw = booster.predict(df[FEATURES])
    ours = pickle.load(open(ART / "calibrator.pkl", "rb")).predict(raw)  # noqa: SIM115
    p, label = ours.copy(), np.full(len(df), "our model", dtype=object)
    has = df.v21_score.notna().to_numpy()
    if decision == "use blend":
        blender = pickle.load(open(ART / "blender.pkl", "rb"))  # noqa: SIM115
        p[has] = blender.predict_proba(blend_x(df.v21_score.to_numpy()[has], raw[has]))[:, 1]
        label[has] = "blend"
    elif decision == "keep bank v2.1":
        p[has] = df.v21_score.to_numpy()[has]
        label[has] = "bank v2.1"
    out = pd.DataFrame(
        {
            "ptp_id": df.ptp_id.to_numpy(),
            "golden_id": df.golden_id.to_numpy(),
            "ptp_created_ts": df.ptp_created_ts.to_numpy(),
            "label_broken": df.label_broken.to_numpy(),
            "p_break": np.round(p, 4),
            "model": label,
        }
    )
    path = s.features_dir / "ptp_test_scores.parquet"
    out.to_parquet(path, index=False)
    print(f"wrote {path} ({len(out)} test promises, {int(has.sum())} with a bank v2.1 score)")
    return out


if __name__ == "__main__":
    main()
