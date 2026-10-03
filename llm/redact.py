"""Redact direct PII before any text leaves the machine. Transcripts are pre-redacted upstream;
agent notes are not. Extend the patterns after profiling real notes (TBC)."""

from __future__ import annotations

import re

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("[EMAIL]", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("[PHONE]", re.compile(r"(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}")),
    ("[CARD]", re.compile(r"\b(?:\d[ -]?){13,19}\b")),
    ("[SIN]", re.compile(r"\b\d{3}[ -]?\d{3}[ -]?\d{3}\b")),
    ("[POSTAL]", re.compile(r"\b[A-CEGHJ-NPR-TVXY]\d[A-CEGHJ-NPR-TV-Z][ -]?\d[A-CEGHJ-NPR-TV-Z]\d\b", re.I)),
    ("[ACCOUNT]", re.compile(r"\b(?:acct|account|a/c)\s*#?\s*\d{4,}\b", re.I)),
]


def redact(text: str, known_names: list[str] | None = None) -> str:
    out = text
    for token, pat in _PATTERNS:
        out = pat.sub(token, out)
    for name in known_names or []:
        if name and len(name) > 1:
            out = re.sub(rf"\b{re.escape(name)}\b", "[NAME]", out, flags=re.I)
    return out
