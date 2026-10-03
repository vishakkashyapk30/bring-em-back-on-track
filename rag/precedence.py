"""D12: conflicts resolve to the highest-authority current document; unresolved -> refuse."""

AUTHORITY = ["regulatory_summary", "policy", "hardship_programme_terms", "procedure", "call_script", "faq"]


def rank(doc_type: str) -> int:
    return AUTHORITY.index(doc_type) if doc_type in AUTHORITY else len(AUTHORITY)
