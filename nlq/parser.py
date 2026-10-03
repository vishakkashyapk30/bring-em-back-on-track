"""Question -> QueryTokens. The offline rule parser is built first (synonyms from metric_definitions,
vocab, relative date phrases vs as_of_date); an LLM provider only improves it."""

from __future__ import annotations

from llm.providers.offline import register
from nlq.schemas import QueryTokens


@register("question_parse")
def parse_offline(inputs: dict) -> dict:
    """inputs: {question, vocabulary, as_of_date}. TODO(WS-B): synonym + fuzzy (rapidfuzz) matching."""
    return QueryTokens(intent="metric", out_of_scope=None).model_dump()


def parse(question: str, role: str) -> QueryTokens:
    from llm.client import complete_json

    out = complete_json("question_parse", 1, {"question": question, "role": role}, "question_tokens")
    out.pop("_meta", None)
    return QueryTokens.model_validate(out)
