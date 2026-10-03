"""Clustering with guards + stable golden IDs.

Guards: two different non-null national_id_hash in one cluster = cannot-link; clusters with > 5 CRM
records or any internal pair < 0.5 go to review instead of chain-merging. On rerun a cluster keeps the
golden_id of the old cluster it overlaps most; merges keep the older ID (aliases in identity_events).
"""

from __future__ import annotations

import pandas as pd

MAX_CRM_RECORDS_PER_CLUSTER = 5


def cluster(edges: pd.DataFrame) -> pd.DataFrame:
    """Return identity_xref rows: golden_id, source_system, source_ref, crm_customer_id, match_method,
    match_probability. TODO(WS-A)."""
    raise NotImplementedError


def assign_stable_ids(new: pd.DataFrame, previous: pd.DataFrame | None) -> pd.DataFrame:
    """G-NNNNNN ids stable across reruns. TODO(WS-A)."""
    raise NotImplementedError
