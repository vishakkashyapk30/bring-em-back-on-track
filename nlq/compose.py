"""Answer composition: template insight from rows (offline) or LLM insight from rows only."""

from llm.providers.offline import register


@register("ask_insight")
def insight_offline(inputs: dict) -> dict:
    """inputs: {question, columns, rows}. TODO(WS-B): top item, total, change vs previous period."""
    return {"insight": "", "followups": []}
