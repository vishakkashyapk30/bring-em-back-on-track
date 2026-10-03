"""Deterministic explanation template: recommendation, rules applied, model evidence (labelled
'model estimate'), what changed, freshness, alternatives. No LLM."""

from decisioning.schemas import Explanation


def explain(action, gate_result, reasons, changes, freshness, alternatives) -> Explanation:
    raise NotImplementedError("TODO(WS-D)")
