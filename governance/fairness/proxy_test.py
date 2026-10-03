"""Proxy test: AUC of each feature group predicting each protected attribute (> 0.65 -> review) + MI."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

THRESHOLD_AUC = 0.65


def group_proxy_auc(features: Sequence[Mapping[str, Any]], protected: Sequence[Mapping[str, Any]],
                    groups: Mapping[str, Sequence[str]], threshold: float = THRESHOLD_AUC) -> dict[str, dict]:
    """For each feature group, the cross-validated AUC of a logistic model predicting each protected attribute
    from that group alone (rows joined on entity_id; multi-class attributes use one-vs-rest macro AUC).

    A group above `threshold` for any attribute gets decision "drop" (V1 section 5: "I drop it or make it coarser";
    design_changes.md #9): training leaves it out (see `dropped_inputs`) AND it goes to a person for review with the
    numbers (`review` is True, `review_note` carries them); otherwise "keep". Returns
    {group: {max_auc, worst_attribute, aucs: {attribute: auc}, decision, review, review_note}}.
    """
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import StratifiedKFold, cross_val_predict
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    prot_by_id = {p["entity_id"]: p for p in protected}
    rows = [(f, prot_by_id[f["entity_id"]]) for f in features if f.get("entity_id") in prot_by_id]
    attributes = sorted({k for _, p in rows for k in p if k != "entity_id"})
    out: dict[str, dict] = {}
    for group, cols in groups.items():
        x = np.array([[float(f.get(c) or 0.0) for c in cols] for f, _ in rows])
        aucs: dict[str, float] = {}
        for attr in attributes:
            pairs = [(i, p.get(attr)) for i, (_, p) in enumerate(rows) if p.get(attr) is not None]
            labels = [str(v) for _, v in pairs]
            classes = sorted(set(labels))
            if len(classes) < 2 or min(labels.count(c) for c in classes) < 5:
                continue
            idx = [i for i, _ in pairs]
            y = np.array([classes.index(v) for v in labels])
            model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000))
            cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=0)
            proba = cross_val_predict(model, x[idx], y, cv=cv, method="predict_proba")
            auc = (roc_auc_score(y, proba[:, 1]) if len(classes) == 2
                   else roc_auc_score(y, proba, multi_class="ovr", average="macro"))
            aucs[attr] = float(auc)
        worst = max(aucs, key=aucs.get) if aucs else None
        max_auc = aucs[worst] if worst else 0.5
        over = max_auc > threshold
        out[group] = {"max_auc": round(max_auc, 4), "worst_attribute": worst, "aucs": aucs,
                      "decision": "drop" if over else "keep", "review": over,
                      "review_note": (f"{group} predicts {worst} (AUC {max_auc:.3f} > {threshold}): dropped from the "
                                      "model input, sent for review") if over else None}
    return out


def dropped_inputs(report: Mapping[str, Any] | None = None) -> set[str]:
    """Model input columns that the latest proxy report dropped (groups decided "drop"). Reads only the aggregate
    report (reports/fairness.json), never a protected attribute. Training calls this to leave those columns out."""
    import json

    from common.config import get_settings

    if report is None:
        path = get_settings().reports_dir / "fairness.json"
        if not path.exists():
            return set()
        report = json.loads(path.read_text()).get("proxy", {})
    return {c.removesuffix("=*") for g in report.get("groups", []) if g.get("decision") == "drop"
            for c in GROUPS.get(g["group"], [])}


# Feature groups audited. The first four are what the promise-break model uses; "cash_stress" is the
# transaction and bureau signal the next-best-action rules read; "case_context" is the delinquency picture.
GROUPS: dict[str, list[str]] = {
    "promise_terms": ["days_to_due_at_creation", "prior_broken_ptp_count", "ptp_sequence_in_case", "reminder_scheduled",
                      "stated_payday_known", "ptp_type=*", "payment_method_promised=*", "ptp_channel=*"],
    "delinquency": ["dpd_at_creation", "overdue_at_creation", "days_in_case", "product=*", "case_product=*"],
    "contact_history": ["attempts_30d", "rpc_30d", "contacts_90d", "complaints_90d", "disputes_90d",
                        "cease_requests_90d", "broken_before_in_case", "kept_before_in_case"],
    "text_signals": ["hardship_mentions_90d", "text_hardship_clear_90d", "text_hardship_possible_90d",
                     "text_dispute_90d", "text_complaint_90d", "last_stated_delay_reason=*"],
    "credit_history": ["bur_score", "bur_util", "bur_delinq_trades", "bur_inq_6m", "bur_stale", "sal_gap_months_3",
                       "sal_avg_credit_3", "sal_gap_last_month", "card_util", "card_min_paid", "card_paid_full",
                       "card_days_late", "card_cycles_delinq", "card_pay_to_min", "snap_util", "snap_pay_to_min",
                       "snap_dpd", "snap_overlimit"],
    "cash_stress": ["nsf_count_mtd", "days_negative_mtd", "high_cost_lender_txn_flag", "ei_deposit_flag",
                    "payroll_delay_days", "payroll_amount_change_pct", "bureau_risk_score", "bnpl_trades_count",
                    "off_us_delinquent_trades"],
}
SAMPLE = 60_000  # customers; the proxy AUC is stable well before this


def _frame():
    """One row per customer (their latest promise in the offline store) with every audited feature, numeric."""
    import duckdb
    import pandas as pd

    from common.config import get_settings

    s = get_settings()
    con = duckdb.connect(str(s.warehouse_path), read_only=True)
    df = con.sql(f"""
        SELECT t.*, o.nsf_count_mtd, o.days_negative_mtd, o.high_cost_lender_txn_flag::int AS high_cost_lender_txn_flag,
               o.ei_deposit_flag::int AS ei_deposit_flag, o.payroll_delay_days, o.payroll_amount_change_pct,
               o.bureau_risk_score, o.bnpl_trades_count, o.off_us_delinquent_trades
        FROM features.f_ptp_offline t LEFT JOIN features.f_customer_online o USING (golden_id)
        QUALIFY row_number() OVER (PARTITION BY t.golden_id ORDER BY t.ptp_created_ts DESC) = 1
        USING SAMPLE reservoir({SAMPLE} ROWS) REPEATABLE (7)""").df()
    con.close()
    groups: dict[str, list[str]] = {}
    for g, cols in GROUPS.items():
        names: list[str] = []
        for c in cols:
            if c.endswith("=*"):
                dummies = pd.get_dummies(df[c[:-2]].fillna("missing").astype(str), prefix=c[:-2], dtype=float)
                df = pd.concat([df, dummies], axis=1)
                names += list(dummies.columns)
            else:
                df[c] = pd.to_numeric(df[c], errors="coerce").astype("float64")
                df[c] = df[c].fillna(df[c].median() if df[c].notna().any() else 0.0)
                names.append(c)
        groups[g] = names
    return df, groups


def run() -> dict:
    """Proxy test on the real feature groups against the audited protected attributes. Returns the report rows."""
    from governance.fairness import auditor

    df, groups = _frame()
    prot = auditor.load()
    prot = prot[prot.golden_id.isin(df.golden_id)]
    feats = [{"entity_id": r["golden_id"], **{c: r[c] for cols in groups.values() for c in cols}}
             for r in df.to_dict("records")]
    protected = [{"entity_id": r["golden_id"], **{a: r[a] for a in auditor.ATTRIBUTES}}
                 for r in prot.to_dict("records")]
    res = group_proxy_auc(feats, protected, groups)
    rows = []
    for g, r in res.items():
        rows.append({"group": g, "n_features": len(groups[g]), "max_auc": r["max_auc"],
                     "worst_attribute": r["worst_attribute"], "decision": r["decision"], "review": r["review"],
                     "review_note": r["review_note"],
                     "aucs": {k: round(v, 4) for k, v in sorted(r["aucs"].items(), key=lambda kv: -kv[1])}})
    return {"customers": len(feats), "threshold": THRESHOLD_AUC, "groups": rows}
