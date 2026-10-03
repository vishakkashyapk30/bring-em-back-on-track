"""Training frame for the promise-break model, from the offline feature store (features.f_ptp_offline: features
as of the moment each promise was made). Time-based split; asserts no protected or leaking columns."""

from __future__ import annotations

import re

import duckdb
import pandas as pd

from common.config import get_settings
from common.protected import assert_no_protected

WIDE_COLS = re.compile(r"_m(0[1-9]|1[0-2])$")

NUMERIC = [
    "days_to_due_at_creation",
    "prior_broken_ptp_count",
    "dpd_at_creation",
    "overdue_at_creation",
    "ptp_sequence_in_case",
    "reminder_scheduled",
    "stated_payday_known",
    "days_in_case",
    "attempts_30d",
    "rpc_30d",
    "contacts_90d",
    "complaints_90d",
    "disputes_90d",
    "hardship_mentions_90d",
    "broken_before_in_case",
    "kept_before_in_case",
    "text_hardship_clear_90d",
    "text_hardship_possible_90d",
    "text_dispute_90d",
    "text_complaint_90d",
]
CATEGORICAL = [
    "ptp_type",
    "payment_method_promised",
    "ptp_channel",
    "product",
    "case_product",
    "last_stated_delay_reason",
]
# Excluded on purpose (leakage or no information), see docs/model_card_ptp_break.md:
# - ptp_amount and ptp_to_overdue_ratio: in this data the promised amount looks back-filled after the outcome.
#   69% of kept promises are for the full overdue amount but only 0.3% of still-open promises are (about 26%
#   expected from the same cohort mix). With them the model scores a fake 0.95 AUC.
# - queue: the case's *current* queue reflects what happened after the promise.
# - entry_dpd (always 1) and due_minus_stated_payday_days (always 0): constant in the release.
# - ids, status and timestamps.
FEATURES = NUMERIC + CATEGORICAL

TRAIN_END = "2026-04-01"  # train: promises made before this date
CALIB_END = "2026-07-01"  # calibrate: Apr to Jun 2026; test: Jul to Sep 2026 (same window as the bank's v2.1 scores)


def check_columns(cols: list[str]) -> None:
    assert_no_protected(cols, "ptp_break training frame")
    leaked = [c for c in cols if WIDE_COLS.search(c)]
    if leaked:
        raise ValueError(f"Wide _m01.._m12 columns leak the future: {leaked}")


def _prep(df: pd.DataFrame) -> pd.DataFrame:
    for c in NUMERIC:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("float64")
    for c in CATEGORICAL:
        df[c] = df[c].fillna("missing").astype("category")
    return df


def build_dataset() -> pd.DataFrame:
    check_columns(FEATURES)
    con = duckdb.connect(str(get_settings().warehouse_path), read_only=True)
    df = con.sql(f"""
        SELECT f.ptp_id, f.case_id, f.golden_id, f.ptp_created_ts, f.label_broken,
               {", ".join("f." + c for c in FEATURES)},
               m.score AS v21_score
        FROM features.f_ptp_offline f
        LEFT JOIN (SELECT ptp_id, arg_max(score, score_date) AS score FROM silver.model_scores
                   WHERE model_name = 'ptp_break' GROUP BY 1) m USING (ptp_id)
        WHERE f.label_broken IS NOT NULL AND NOT f.excluded_outage""").df()
    con.close()
    df = _prep(df)
    ts = pd.to_datetime(df["ptp_created_ts"])
    df["split"] = "train"
    df.loc[ts >= TRAIN_END, "split"] = "calib"
    df.loc[ts >= CALIB_END, "split"] = "test"
    return df


def live_frame() -> pd.DataFrame:
    """Open promises with the SAME features evaluated as of the scoring time (features.f_ptp_online)."""
    con = duckdb.connect(str(get_settings().warehouse_path), read_only=True)
    df = con.sql(f"""SELECT ptp_id, case_id, golden_id, ptp_due_date, ptp_amount AS amount_cad,
                            {", ".join(FEATURES)} FROM features.f_ptp_online""").df()
    con.close()
    return _prep(df)
