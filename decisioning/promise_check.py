"""A2 promise check + what-if: re-score the case's promise with a different date and report how many days it sits
before the customer's payday. Always labelled 'model estimate, not cause and effect'. Nothing is saved."""

from __future__ import annotations

from datetime import date

LABEL = "model estimate, not cause and effect"


def days_before_payday(due: date | None, payday: date | None) -> int | None:
    """How many days the promise falls before the customer's payday (positive = before, negative = after).
    None when either date is unknown."""
    if due is None or payday is None:
        return None
    return (payday - due).days


def what_if(case_id: str, ptp_amount: float, ptp_due_date: str, split: list | None = None) -> dict:
    """Break risk now vs if the promise were due on `ptp_due_date`. The model does not use the promised amount
    (in this data it is filled in after the outcome), so only the date moves the score."""
    import json
    import pickle

    import lightgbm as lgb
    import numpy as np
    import pandas as pd

    from models.ptp_break.dataset import FEATURES, live_frame
    from models.ptp_break.train import ART, blend_x

    df = live_frame()
    df = df[df.case_id == case_id].sort_values("ptp_due_date")
    if df.empty:
        return {"case_id": case_id, "error": "No open promise on this case to re-score", "label": LABEL, "saved": False}
    row = df.iloc[[0]].copy()
    meta = json.loads((ART / "meta.json").read_text())
    for c, cats in meta["categories"].items():
        row[c] = pd.Categorical(row[c].astype(str), categories=cats)
    booster = lgb.Booster(model_file=str(ART / "ptp_break.txt"))
    cal = pickle.load(open(ART / "calibrator.pkl", "rb"))  # noqa: SIM115
    blender = pickle.load(open(ART / "blender.pkl", "rb"))  # noqa: SIM115
    old_due = pd.Timestamp(row.ptp_due_date.iloc[0]).normalize()
    new_due = pd.Timestamp(ptp_due_date).normalize()

    v21 = _v21(row.ptp_id.iloc[0])
    payday = _stated_payday(row.ptp_id.iloc[0])
    base_days = float(row.days_to_due_at_creation.iloc[0])

    def score(due: pd.Timestamp) -> float:
        r = row.copy()
        r["days_to_due_at_creation"] = base_days + float((due - old_due).days)  # same promise, later or earlier date
        raw = booster.predict(r[FEATURES])
        if v21 is not None:
            return float(blender.predict_proba(blend_x(np.array([v21]), raw))[0, 1])
        return float(cal.predict(raw)[0])

    before, after = score(old_due), score(new_due)
    return {
        "case_id": case_id,
        "p_break_before": round(before, 3),
        "p_break_after": round(after, 3),
        "due_before": str(old_due.date()),
        "due_after": str(new_due.date()),
        "days_before_payday_before": days_before_payday(old_due.date(), payday),
        "days_before_payday_after": days_before_payday(new_due.date(), payday),
        "label": LABEL,
        "saved": False,
        "note": "Only the date changes the score. The promised amount is not a model input.",
    }


def _v21(ptp_id: str):
    import duckdb

    from common.config import get_settings

    con = duckdb.connect(str(get_settings().warehouse_path), read_only=True)
    try:
        r = con.execute(
            "SELECT arg_max(score, score_date) FROM silver.model_scores WHERE model_name='ptp_break' AND ptp_id=?",
            [ptp_id],
        ).fetchone()
    finally:
        con.close()
    return None if not r or r[0] is None else float(r[0])


def _stated_payday(ptp_id: str) -> date | None:
    """The payday the customer gave when making this promise (promises_to_pay.customer_stated_income_date)."""
    import duckdb

    from common.config import get_settings

    con = duckdb.connect(str(get_settings().warehouse_path), read_only=True)
    try:
        r = con.execute(
            "SELECT customer_stated_income_date FROM silver.promises_to_pay WHERE ptp_id = ?", [ptp_id]
        ).fetchone()
    finally:
        con.close()
    if not r or r[0] is None:
        return None
    return r[0].date() if hasattr(r[0], "date") else r[0]
