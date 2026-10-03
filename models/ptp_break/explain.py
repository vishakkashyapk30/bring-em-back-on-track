"""SHAP top-3 reason codes + plain-English text, same shape as model_scores.top_reason_*."""

REASON_TEXT = {  # TODO(WS-C): one template per feature
    "payroll_delay_days": "Payroll deposit {value} days late",
    "ptp_broken_count_90d": "{value} broken promise(s) in 90 days",
    "risk_score_delta_90d": "Bureau score {direction} {abs_value} in 90 days",
}


def reason_codes(row, shap_values, k: int = 3) -> list[dict]:
    raise NotImplementedError
