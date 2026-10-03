"""Refuse by construction: protected attributes, direct PII, off-allowlist tokens,
bulk-PII intents. Every refusal is audited with a reason code."""

from __future__ import annotations

import re

from common.protected import find_forbidden
from nlq.schemas import QueryTokens

DIRECT_PII = {"phone", "phone number", "email", "address", "sin", "national id", "date of birth", "dob"}
_BULK_PII = re.compile(r"\b(list|export|dump|show)\b.*\b(phone|email|address|sin|dob|date of birth)", re.I)


def check(question: str, tokens: QueryTokens | None) -> str | None:
    """Return a user-facing refusal reason, or None if allowed."""
    if _BULK_PII.search(question):
        return "Direct personal details (phone, email, address) aren't available through Ask."
    if tokens is not None:
        if tokens.out_of_scope:
            return f"'{tokens.out_of_scope}' is outside the data you're allowed to query."
        fields = list(tokens.dimensions) + [f.field for f in tokens.filters]
        bad = find_forbidden(fields)
        if bad:
            return f"{', '.join(sorted(bad))} is a protected attribute and can't be used."
    # also catch protected names typed directly in the question
    words = set(re.findall(r"[a-z_]+", question.lower()))
    bad = find_forbidden(words) | ({"gender", "marital", "citizenship", "accent"} & words)
    if bad:
        return "Protected attributes (e.g. gender, marital status, citizenship, accent) can't be queried."
    return None
