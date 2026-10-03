"""Cited answers. Offline = extractive quotes with doc_id §section; LLM = grounded answer."""

from llm.providers.offline import register


@register("rag_answer")
def answer_offline(inputs: dict) -> dict:
    """inputs: {question, sections:[{doc_id, section, text}]}. TODO(WS-B): pick best sections, quote."""
    secs = inputs.get("sections") or []
    if not secs:
        return {"answer": None, "citations": [], "refused": True,
                "refusal_reason": "No current policy section answers this question."}
    return {"answer": None, "citations": [{"doc_id": s["doc_id"], "section": s["section"],
                                           "quote": s["text"][:400]} for s in secs[:3]],
            "refused": False, "refusal_reason": None}
