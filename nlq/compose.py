"""Answer composition: template insight (offline) or an LLM insight from the rows only (nlq/llm_sql.write_insight)."""

from llm.providers.offline import register


@register("ask_insight")
def insight_offline(inputs: dict) -> dict:
    """inputs: {question, sql, columns, rows}. Offline there is no written insight: the caller uses its template."""
    return {"insight": "", "numbers_used": [], "followups": []}
