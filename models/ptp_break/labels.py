"""Label: ptp_status in (broken, partially_kept) after ptp_due_date + grace_days -> 1; kept -> 0;
open/cancelled excluded; promises overlapping a payment-posting outage in ops_events dropped."""

import pandas as pd


def build_labels() -> pd.DataFrame:
    raise NotImplementedError("TODO(WS-C)")
