"""Cited policy answers. Offline = extractive: the most relevant sentences of the best current section, with
doc_id §section citations; an LLM provider can replace the wording later (same output schema). No citation, no
answer: if nothing relevant is retrieved, refuse."""

from __future__ import annotations

import re

from llm.providers.offline import register
from rag.retrieve import Hit, expand, idf, retrieve, tokens

MIN_SCORE = 2.0
SUBSTITUTES = {"sue": ["legal", "court", "lawsuit", "litigation"], "lawsuit": ["legal", "court"]}


# Topics the 19 current documents never mention: refuse instead of answering from the nearest section.
# (Checked against the corpus; add a term here only after confirming no document covers it.)
NOT_COVERED = re.compile(
    r"\b(collection agenc\w*|agency placement|placed with an? agenc\w*|third[- ]party collect\w*|garnish\w*|repossess\w*|"
    r"statute of limitations?|voice ?mails?|deceased|passed away|died|estate|debt (sale|buyer)s?)\b", re.I)

LIST_ITEM = re.compile(r"^\s*(?:\d+\.|[-*])\s+")
DUTY_Q = re.compile(r"\b(must|should|what (do|does|should)|what to do|before)\b", re.I)


def _sentences(text: str) -> list[str]:
    """List items stay separate; hard-wrapped paragraph lines are joined before splitting into sentences."""
    units, para = [], []

    def flush() -> None:
        if para:
            joined = " ".join(para)
            units.extend(s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", joined) if s.strip())
            para.clear()

    for line in re.sub(r"\*\*|`", "", text).split("\n"):
        line = line.strip()
        if not line:
            flush()
        elif LIST_ITEM.match(line):
            flush()
            units.append(LIST_ITEM.sub("", line))
        elif units and not para and LIST_ITEM.match(line) is None and units[-1] and not units[-1].endswith((".", ":", "?")):
            units[-1] += " " + line  # continuation of a wrapped list item
        else:
            para.append(line)
    flush()
    return units


def _duty_list(text: str) -> str | None:
    """The numbered list that follows a 'must/should' lead-in, e.g. 'When a customer states a hardship the agent must:'."""
    lines = re.sub(r"\*\*|`", "", text).split("\n")
    for i, line in enumerate(lines):
        if re.search(r"\b(must|should)\b.*:\s*$", line):
            items = []
            for nxt in lines[i + 1:]:
                if re.match(r"^\s*\d+\.\s+", nxt):
                    items.append(LIST_ITEM.sub("", nxt.strip()).rstrip("."))
                elif items:
                    break
            if items:
                return "; ".join(items) + "."
    return None


def _best_sentences(question: str, hit: Hit, n: int = 2) -> str:
    if DUTY_Q.search(question):
        duty = _duty_list(hit.section.text)
        if duty:
            return duty
    q = set(expand(question))
    sents = _sentences(hit.section.text)
    scored = sorted(enumerate(sents), key=lambda x: (-sum(idf(t) for t in q & set(tokens(x[1]))), x[0]))
    keep = sorted(i for i, _ in scored[:n])
    return " ".join(sents[i] for i in keep)


def _MAX_IDF() -> float:  # noqa: N802
    from rag.retrieve import _index

    return max(_index().idf.values(), default=0.0)


def _covers(question: str, text: str) -> bool:
    """The answer must contain at least one of the question's rarer terms (or a synonym)."""
    text_tokens = set(tokens(text))
    # key words the corpus never uses (e.g. "sue"): one of their substitutes must appear in the answer
    for t in tokens(question):
        if t in SUBSTITUTES and not (set(SUBSTITUTES[t]) & text_tokens):
            return False
    q = set(expand(question))
    # content words the documents never use (e.g. "pet insurance") count as uncovered, at the corpus's highest
    # rarity weight, so a question about something the policies don't cover is refused instead of answered
    unseen = {t for t in tokens(question) if idf(t) == 0.0 and t not in SUBSTITUTES and len(t) > 2 and not t.isdigit()}
    total = sum(idf(t) for t in q) + _MAX_IDF() * len(unseen)
    if not total:
        return False
    matched = q & text_tokens
    ratio = sum(idf(t) for t in matched) / total
    return ratio >= 0.3 or (len(matched) >= 2 and ratio >= 0.15)


def answer_question(question: str, product: str | None = None, province: str | None = None,
                    language: str | None = None) -> dict:
    if NOT_COVERED.search(question):
        return {"answer": None, "citations": [], "refused": True,
                "refusal_reason": "The current policy documents don't cover this topic."}
    hits = retrieve(question, language=language, product=product, province=province)
    if not hits or hits[0].score < MIN_SCORE:
        return {"answer": None, "citations": [], "refused": True,
                "refusal_reason": "No current policy section answers this question."}
    best = next((h for h in hits if _covers(question, _best_sentences(question, h))), None)
    if best is None:
        return {"answer": None, "citations": [], "refused": True,
                "refusal_reason": "No current policy section covers this question."}
    cites = [best]
    # a second, independent source when it is nearly as relevant (e.g. policy + FAQ, policy + QA checklist)
    for h in hits:
        if h is not best and h.section.doc_id != best.section.doc_id and h.score >= 0.6 * hits[0].score and len(cites) < 2:
            if h.section.authority <= 5:
                cites.append(h)
    text = _best_sentences(question, best)
    if re.match(r"^(does|do|is|are|can|should|must)\b", question.strip(), re.I):
        lowered = text.lower()
        # only a clear negation earns a "No." prefix; never assert "Yes" from absence of evidence
        if re.search(r"\b(does not|doesn't|is not|isn't|not needed|not allowed|never|stops)\b", lowered):
            text = "No. " + text if not lowered.startswith("no") else text
    return {"answer": text,
            "citations": [{"doc_id": h.section.doc_id, "section": h.section.section,
                           "quote": _best_sentences(question, h, 1)} for h in cites],
            "refused": False, "refusal_reason": None}


@register("rag_answer")
def answer_offline(inputs: dict) -> dict:
    return answer_question(inputs["question"])


def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", re.sub(r"\*\*|`", "", t).lower()).strip()


def answer_with_llm(question: str, product: str | None = None, province: str | None = None,
                    language: str | None = None) -> dict:
    """Policy answer written by the configured LLM from the retrieved sections, accepted only when it is grounded:
    every citation must be a section that was retrieved and every quote must appear word for word in that section.
    Anything else (no LLM, unreachable, ungrounded, refused) falls back to the extractive answer above, so the
    answer is never worse than the offline one. Topics the documents never cover are refused before the model runs."""
    from common.config import get_settings

    base = answer_question(question, product=product, province=province, language=language)
    if get_settings().llm_provider == "offline" or NOT_COVERED.search(question):
        return base
    hits = retrieve(question, language=language, product=product, province=province)[:3]
    if not hits:
        return base
    try:
        from llm.client import complete_json

        out = complete_json(
            "rag_answer", 1,
            {"question": question, "sections": [{"doc_id": h.section.doc_id, "section": h.section.section,
                                                 "text": h.section.text} for h in hits]}, "rag_answer")
    except Exception:  # noqa: BLE001 - an LLM problem must never break policy answers
        return base
    if out.get("_meta", {}).get("provider") == "offline" or out.get("refused") or not out.get("answer"):
        return base
    by_id = {(h.section.doc_id, h.section.section): _norm(h.section.text) for h in hits}
    cites = out.get("citations") or []
    if not cites or any((c.get("doc_id"), c.get("section")) not in by_id
                        or not _norm(c.get("quote", "")) or _norm(c["quote"]) not in by_id[(c["doc_id"], c["section"])]
                        for c in cites):
        return base
    return {"answer": out["answer"].strip(),
            "citations": [{"doc_id": c["doc_id"], "section": c["section"], "quote": c["quote"]} for c in cites],
            "refused": False, "refusal_reason": None, "by_llm": True}
