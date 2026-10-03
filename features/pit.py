"""Point-in-time join: feature values known at decision time (for promises, ptp_created_ts)."""

import pandas as pd


def as_of_join(spine: pd.DataFrame, features: pd.DataFrame, entity: str, ts_col: str) -> pd.DataFrame:
    """Join each spine row to the latest feature row with available_ts <= spine[ts_col]. TODO(WS-C):
    DuckDB ASOF JOIN."""
    raise NotImplementedError
