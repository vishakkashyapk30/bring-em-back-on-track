"""Plain-English reason codes for a break-risk score, from LightGBM's exact per-feature contributions (TreeSHAP,
`pred_contrib=True`). Only drivers that push risk UP are shown as reasons."""

from __future__ import annotations

import math

TEXT = {
    "prior_broken_ptp_count": lambda v: f"{int(v)} earlier promise(s) broken",
    "broken_before_in_case": lambda v: f"{int(v)} broken promise(s) on this case already",
    "kept_before_in_case": lambda v: f"{int(v)} promise(s) kept on this case so far",
    "dpd_at_creation": lambda v: f"{int(v)} days past due when the promise was made",
    "ptp_to_overdue_ratio": lambda v: f"promise covers {v:.0%} of the overdue amount",
    "days_to_due_at_creation": lambda v: f"due {int(v)} days after it was made",
    "due_minus_stated_payday_days": lambda v: (
        f"due {abs(int(v))} days before the stated payday" if v < 0 else f"due {int(v)} days after the stated payday"
    ),
    "stated_payday_known": lambda v: "customer gave a payday" if v else "no payday given",
    "attempts_30d": lambda v: f"{int(v)} outbound attempts in the last 30 days",
    "rpc_30d": lambda v: f"{int(v)} conversations in the last 30 days",
    "contacts_90d": lambda v: f"{int(v)} contacts in the last 90 days",
    "complaints_90d": lambda v: f"{int(v)} complaint(s) in the last 90 days",
    "disputes_90d": lambda v: f"{int(v)} dispute(s) in the last 90 days",
    "hardship_mentions_90d": lambda v: f"hardship mentioned {int(v)} time(s) recently",
    "text_hardship_clear_90d": lambda v: f"notes or calls describe hardship ({int(v)})",
    "text_hardship_possible_90d": lambda v: f"notes or calls hint at hardship ({int(v)})",
    "text_dispute_90d": lambda v: f"notes or calls mention a dispute ({int(v)})",
    "text_complaint_90d": lambda v: f"notes or calls mention a complaint ({int(v)})",
    "days_in_case": lambda v: f"case open {int(v)} days",
    "entry_dpd": lambda v: f"entered collections at {int(v)} days past due",
    "ptp_amount": lambda v: f"promised ${v:,.0f}",
    "overdue_at_creation": lambda v: f"${v:,.0f} overdue when promised",
    "ptp_sequence_in_case": lambda v: f"promise number {int(v)} on this case",
    "reminder_scheduled": lambda v: "reminder scheduled" if v else "no reminder scheduled",
    "bur_score": lambda v: f"bureau score {int(v)}",
    "bur_util": lambda v: f"bureau revolving utilisation {v:.0%}",
    "bur_delinq_trades": lambda v: f"{int(v)} delinquent trade(s) on the bureau",
    "bur_inq_6m": lambda v: f"{int(v)} hard credit inquiries in 6 months",
    "bur_stale": lambda v: "bureau score is stale" if v else "bureau score is current",
    "sal_gap_months_3": lambda v: f"no salary credit in {int(v)} of the last 3 months",
    "sal_avg_credit_3": lambda v: f"salary credits average ${v:,.0f} a month",
    "sal_gap_last_month": lambda v: "no salary credit last month" if v else "salary credited last month",
    "card_util": lambda v: f"card balance is {v:.0%} of the limit",
    "card_min_paid": lambda v: "last card minimum was paid" if v else "last card minimum was not paid",
    "card_paid_full": lambda v: "last card statement paid in full" if v else "last card statement not paid in full",
    "card_days_late": lambda v: f"last card payment was {int(v)} days late",
    "card_cycles_delinq": lambda v: f"{int(v)} card cycle(s) delinquent",
    "card_pay_to_min": lambda v: f"paid {v:.0%} of the card minimum last cycle",
    "snap_util": lambda v: f"account balance is {v:.0%} of its limit",
    "snap_pay_to_min": lambda v: f"paid {v:.0%} of the minimum at the last month-end",
    "snap_dpd": lambda v: f"{int(v)} days past due at the last month-end",
    "snap_overlimit": lambda v: "over limit at the last month-end" if v else "within limit at the last month-end",
}
CAT_TEXT = {
    "ptp_type": "promise type: {}",
    "payment_method_promised": "payment method: {}",
    "ptp_channel": "made by {}",
    "product": "product: {}",
    "case_product": "case product: {}",
    "last_stated_delay_reason": "stated reason: {}",
}


def describe(feature: str, value) -> str:
    if feature in CAT_TEXT:
        return CAT_TEXT[feature].format(str(value).replace("_", " "))
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return f"{feature.replace('_', ' ')}: missing"
    fn = TEXT.get(feature)
    return fn(float(value)) if fn else f"{feature.replace('_', ' ')} = {value}"


def reason_codes(row: dict, contributions: dict[str, float], k: int = 3) -> list[dict]:
    """Top-k features that raise the risk, with plain text and contribution (log-odds)."""
    up = sorted(((f, c) for f, c in contributions.items() if c > 0), key=lambda x: -x[1])[:k]
    return [
        {"code": f, "text": describe(f, row.get(f)), "contribution": round(float(c), 4), "kind": "model"} for f, c in up
    ]
