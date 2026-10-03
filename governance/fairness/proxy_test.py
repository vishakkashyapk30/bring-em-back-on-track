"""Proxy test: AUC of each feature group predicting each protected attribute (> 0.65 -> review) + MI."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

THRESHOLD_AUC = 0.65


def group_proxy_auc(features: Sequence[Mapping[str, Any]], protected: Sequence[Mapping[str, Any]],
                    groups: Mapping[str, Sequence[str]], threshold: float = THRESHOLD_AUC) -> dict[str, dict]:
    """For each feature group, the cross-validated AUC of a logistic model predicting each protected attribute
    from that group alone (rows joined on entity_id; multi-class attributes use one-vs-rest macro AUC).

    A group above `threshold` for any attribute gets decision "review" (design_changes.md #9, D10: the proxy test
    triggers a review instead of an automatic drop); otherwise "keep". Returns
    {group: {max_auc, worst_attribute, aucs: {attribute: auc}, decision}}.
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
        out[group] = {"max_auc": round(max_auc, 4), "worst_attribute": worst, "aucs": aucs,
                      "decision": "review" if max_auc > threshold else "keep"}
    return out


def run() -> dict:
    raise NotImplementedError("TODO(WS-H)")
