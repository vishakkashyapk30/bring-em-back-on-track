"""Hardship program eligibility, rules only. The LLM never decides eligibility.
Checks per current program (effective_to = 9999-12-31, product_types match): min_hardship_level, max_dpd,
min_months_on_book, max_uses_12m, excludes_insolvency, excludes_broken_plan_90d, requires_income_evidence."""


def check(case_id: str) -> list[dict]:
    """[{program_id, eligible, rules:[{rule, passed, value, limit}], payment_reduction_pct, ...}]. TODO(WS-D)."""
    raise NotImplementedError
