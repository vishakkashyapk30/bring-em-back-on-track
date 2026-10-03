"""A2 promise check + what-if: days between promised date and stated/expected payday; re-score with the
model. Always labelled 'model estimate, not cause and effect'."""

LABEL = "model estimate, not cause and effect"


def what_if(case_id: str, ptp_amount: float, ptp_due_date: str, split: list | None = None) -> dict:
    raise NotImplementedError("TODO(WS-D)")
