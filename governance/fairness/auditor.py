"""The restricted auditor view: protected attributes per golden ID, for auditing only.

This is the single place that reads `silver.stg_customers_protected`. Nothing outside `governance/fairness/` may
import it, and the audit reports it feeds contain aggregates only (groups under `suppression_min_group` hidden).
"""

from __future__ import annotations

import duckdb
import pandas as pd

from common.config import get_settings

# What we audit. `household_size` and `dependants_count` are binned so groups are big enough to read.
ATTRIBUTES = [
    "gender_code",
    "age_band",
    "marital_status",
    "citizenship_status",
    "newcomer_program_flag",
    "accessibility_needs_flag",
    "vulnerability_type",
    "household_size",
    "dependants_count",
]


def _bin_count(s: pd.Series) -> pd.Series:
    n = pd.to_numeric(s, errors="coerce")
    return n.map(lambda v: "unknown" if pd.isna(v) else ("4+" if v >= 4 else str(int(v))))


def load() -> pd.DataFrame:
    """One row per golden ID (the smallest CRM ID in the cluster), with the audited attributes as short strings."""
    con = duckdb.connect(str(get_settings().warehouse_path), read_only=True)
    df = con.sql(f"""
        SELECT g.golden_id, {", ".join("p." + a for a in ATTRIBUTES)}
        FROM silver.stg_customers_protected p JOIN identity.crm_golden g USING (crm_customer_id)
        QUALIFY row_number() OVER (PARTITION BY g.golden_id ORDER BY p.crm_customer_id) = 1""").df()
    con.close()
    for a in ("household_size", "dependants_count"):
        df[a] = _bin_count(df[a])
    df["vulnerability_type"] = df["vulnerability_type"].fillna("none")
    for a in ATTRIBUTES:
        df[a] = df[a].astype("string").fillna("unknown")
    return df
