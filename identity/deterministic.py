"""Pass 1: exact-key links (weak supervision, not ground truth; D4).

Keys: national_id_hash across CRM records (if the salt is shared, TBC); duplicate_of_crm_id;
account_monthly_snapshot.crm_customer_id; external.bank_subject_ref = deposit src_customer_ref.
"""

from __future__ import annotations

import pandas as pd


def deterministic_links() -> pd.DataFrame:
    """Return edges (left_ref, left_system, right_ref, right_system, evidence). TODO(WS-A)."""
    raise NotImplementedError
