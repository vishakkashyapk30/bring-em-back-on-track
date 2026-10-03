"""Score open promises with the chosen model (see reports/model_eval.json "decision") using the online feature
store, and attach plain-English reasons. Writes data/features/ptp_scores.parquet for the NBA service.
Run: python -m models.ptp_break.score"""

from __future__ import annotations

import json
import pickle

import duckdb
import lightgbm as lgb
import numpy as np
import pandas as pd

from common.config import get_settings
from models.ptp_break.dataset import FEATURES, live_frame
from models.ptp_break.explain import reason_codes
from models.ptp_break.train import ART, FALLBACK, blend_x

BANDS = [(0.35, "low"), (0.55, "medium"), (0.75, "high"), (1.01, "very_high")]


def band(p: float) -> str:
    return next(b for t, b in BANDS if p < t)


def main() -> None:
    s = get_settings()
    meta = json.loads((ART / "meta.json").read_text())
    decision = json.loads((s.reports_dir / "model_eval.json").read_text())["decision"]
    df = live_frame()
    for c, cats in meta["categories"].items():
        df[c] = pd.Categorical(df[c].astype(str), categories=cats)
    booster = lgb.Booster(model_file=str(ART / "ptp_break.txt"))
    raw = booster.predict(df[FEATURES])
    contrib = booster.predict(df[FEATURES], pred_contrib=True)[:, :-1]

    con = duckdb.connect(str(s.warehouse_path), read_only=True)
    v21 = con.sql("""SELECT ptp_id, arg_max(score, score_date) AS v21, arg_max(top_reason_1_text, score_date) AS r1,
                            arg_max(top_reason_2_text, score_date) AS r2
                     FROM silver.model_scores WHERE model_name = 'ptp_break' GROUP BY 1""").df()
    con.close()
    df = df.merge(v21, on="ptp_id", how="left")
    # Fallback for promises the bank did not score: our calibrated model alone (labelled per row).
    ours = pickle.load(open(ART / "calibrator.pkl", "rb")).predict(raw)
    has = df.v21.notna().to_numpy()
    p, label = ours.copy(), np.full(len(df), "our model (no bank v2.1 score)", dtype=object)
    if decision == "use blend" and has.any():  # nothing to blend when the bank scored no promise
        blender = pickle.load(open(ART / "blender.pkl", "rb"))
        p[has] = blender.predict_proba(blend_x(df.v21.to_numpy()[has], raw[has]))[:, 1]
        label[has] = "blend of the bank's v2.1 and our model"
    elif decision == "use ours" or (decision == "use blend" and not has.any()):
        label[:] = "our model"
    else:
        p[has] = df.v21.to_numpy()[has]
        label[has] = "bank v2.1"

    rows = []
    for i, r in enumerate(df.to_dict("records")):
        reasons = reason_codes(r, dict(zip(FEATURES, contrib[i], strict=True)))
        bank = [
            {"code": "bank_v2_1", "text": t, "contribution": None, "kind": "model"}
            for t in (r.get("r1"), r.get("r2"))
            if isinstance(t, str) and t
        ]
        rows.append(
            {
                "ptp_id": r["ptp_id"],
                "case_id": r["case_id"],
                "golden_id": r["golden_id"],
                "ptp_due_date": r["ptp_due_date"],
                "amount_cad": r["amount_cad"],
                "p_break": round(float(p[i]), 4),
                "band": band(float(p[i])),
                "v21_score": r.get("v21"),
                "model": label[i],
                "reasons_json": json.dumps(reasons + bank[:1]),
            }
        )
    out = s.features_dir / "ptp_scores.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(out, index=False)
    rp = s.reports_dir / "model_eval.json"
    if rp.exists():  # tell the Monitoring page and model card how many live scores used the fallback
        report = json.loads(rp.read_text())
        report.setdefault("fallback", FALLBACK)
        report["scoring"] = {
            "open_promises": len(rows),
            "with_bank_v2_1": int(has.sum()),
            "fallback_ours": int((~has).sum()),
            "fallback": FALLBACK,
        }
        rp.write_text(json.dumps(report, indent=2))
    print(
        f"scored {len(rows)} open promises ({int(has.sum())} with v2.1, {int((~has).sum())} on the fallback) -> {out}"
    )


if __name__ == "__main__":
    main()
