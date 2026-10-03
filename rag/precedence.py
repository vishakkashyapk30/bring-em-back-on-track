"""D12: conflicts resolve to the highest-authority current document; unresolved -> refuse."""

# The release's regulatory summary (REG-SUM-001) itself says to treat POL-COLL-001 as the rule set, so bank policy
# ranks first; programme terms and procedures implement policy; scripts and the FAQ are lowest (they go stale).
AUTHORITY = ["policy", "regulatory_summary", "hardship_programme_terms", "procedure", "incident_report",
             "release_note", "data_contract", "call_script", "faq"]


def rank(doc_type: str) -> int:
    return AUTHORITY.index(doc_type) if doc_type in AUTHORITY else len(AUTHORITY)
