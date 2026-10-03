"""Pass 2: Splink 4 (DuckDB backend) probabilistic linking across CRM, cards, loans, deposits, bureau.

Comparisons: name vs cardholder_name_raw / borrower_name_raw / holder_name_raw, DOB, phone, postal,
pad_source_account (evidence, not proof). Train with EM; seed m/u from pass-1 links.
"""

from __future__ import annotations

import pandas as pd

AUTO_LINK_THRESHOLD = 0.99  # TBC: set for >= 99.5% precision on eval/labels/identity_pairs.csv
REVIEW_FLOOR = 0.50  # below = reject; between = steward review queue


def build_linker(records: pd.DataFrame):
    """TODO(WS-A): splink.Linker(records, SettingsCreator(...), DuckDBAPI())."""
    raise NotImplementedError


def score_pairs(linker) -> pd.DataFrame:
    raise NotImplementedError
