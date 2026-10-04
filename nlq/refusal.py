"""Refuse by construction: protected attributes and their proxies, direct personal details, and anything outside
collections data. Every refusal is audited by the caller."""

from __future__ import annotations

import re

from common.protected import find_forbidden
from nlq.schemas import QueryTokens

# Always refused: asking for or segmenting by these is never a collections need.
PROTECTED_STRICT = re.compile(
    r"\b(gender|sex|male|female|marital|married|citizenship|citizens?|immigrants?|newcomers?|refugees?|religion|"
    r"religious|race|racial|ethnic(ity)?|accents?)\b", re.I)
# Refused only when used to segment, list or rank customers (policy questions about them are fine).
PROTECTED_SOFT = re.compile(
    r"\b(disabilit(y|ies)|household size|dependants?|children|pregnan\w*|age|age group|age band|older|younger|"
    r"seniors|accessibility)\b", re.I)
SEGMENTING = re.compile(r"\b(by|list|breakdown|split|compare|rank|which customers|how many|share|rate|percentage|"
                        r"segment|per)\b", re.I)
PII_OBJECTS = (r"names|customer name|phone numbers?|emails|email addresses|home addresses|addresses|dates? of birth|birth ?dates?|dobs?|"
               r"social insurance numbers?|sin numbers?|sin|contact details|national id(?:entifier)?s?(?: hash(?:es)?)?")
PII_REQUEST = re.compile(
    rf"\b(export|list|give me|show|download|dump|extract|pull)\b.{{0,60}}\b({PII_OBJECTS})\b", re.I)
# Uses the data contract does not allow (docs/contracts/c360_customer.v1.yaml, not_allowed), and writes (Ask is
# read-only). Matched on wording that asks for the use, so policy questions about these topics still get answered.
MARKETING_USE = re.compile(r"\b(market\b(?! share)|marketing (campaign|list|offer)s?|cross[- ]?sell\w*|up[- ]?sell\w*)",
                           re.I)
CREDIT_DECISION = re.compile(
    r"\b(increase|raise|lower|reduce|decrease|change|set|approve|decline|grant)\b.{0,30}\bcredit (limit|line)s?\b|"
    r"\bcredit (decision|limit (increase|decrease|change))s?\b|\b(approve|decline|grant)\b.{0,20}\b(loans?|credit)\b",
    re.I)
WRITE_REQUEST = re.compile(
    r"^\s*(please\s+)?(delete|remove|erase|purge|drop|truncate|update|insert|modify|overwrite|alter|edit|change|set|"
    r"mark|close|cancel|waive|reverse)\b", re.I)
# Asking Ask to act on customers. Actions go through the queue and the next best action card, with a person approving.
ACTION_REQUEST = re.compile(
    r"^\s*(please\s+)?(send|text|message|notify|schedule|assign|escalate|flag|transfer|email (the|all|every|each|them)|"
    r"call (the|all|every|each|him|her|them)|contact (the|all|every|each|them))\b", re.I)
PROXY_DECISION = re.compile(
    r"\b(stop offering|stop|deny|exclude|refuse|restrict|withhold|cut off|target|rank|prioriti[sz]e|call first|"
    r"charge more)\b.{0,80}\b(fsas?|postal (areas?|codes?)|neighbou?rhoods?|areas?|regions?|citizenship|newcomers?|"
    r"gender|age|accent|language)\b", re.I)
PROXY_DECISION_REV = re.compile(
    r"\b(fsas?|postal (areas?|codes?)|neighbou?rhoods?|citizenship|newcomers?|gender|accent)\b.{0,80}\b(stop offering|"
    r"stop|deny|exclude|refuse|restrict|withhold|cut off|target|rank|prioriti[sz]e|called first|call first)\b", re.I)
OUT_OF_SCOPE = re.compile(
    r"\b(weather|forecast|stock price|sports?|recipe|movie|joke|horoscope|lottery|bitcoin|crypto|election)\b", re.I)


# Ask reports what happened. It doesn't forecast; the bank's promise-break score is the one prediction it can list.
FORECAST = re.compile(r"\b(forecast\w*|predict\w*|will (the )?(economy|market|rates?|inflation|unemployment)\b|recession|projection|projected|going to|who will|(customers?|accounts?|cases?|promises?) will|"
    r"will .{0,30}\b(default|break|cure|roll|pay|miss)\b)", re.I)


def check(question: str, tokens: QueryTokens | None = None) -> str | None:
    """Return a user-facing refusal reason, or None if the question may be answered."""
    q = question
    if OUT_OF_SCOPE.search(q):
        return "Outside scope: I only answer questions about collections data and policy."
    if FORECAST.search(q) and not re.search(r"(most )?likely to break|break(ing)? a promise", q, re.I):
        return "Refused: Ask reports what has happened in the data; it doesn't forecast or predict outcomes."
    if PROXY_DECISION.search(q) or PROXY_DECISION_REV.search(q):
        return ("Refused: deciding treatment by postal area or a personal characteristic is a protected-ground "
                "proxy and would treat customers unfairly.")
    # every refusal names the part of the question that isn't allowed (V1 §4 step 2)
    protected = [m.group(0) for m in PROTECTED_STRICT.finditer(q)] + sorted(find_forbidden(re.findall(r"[a-z_]+", q.lower())))
    if not protected and SEGMENTING.search(q):
        protected = [m.group(0) for m in PROTECTED_SOFT.finditer(q)]
    if protected:
        return (f"Refused: protected attributes can't be queried or used (asked about: {', '.join(dict.fromkeys(protected))}).")
    if PII_REQUEST.search(q):
        asked = ", ".join(dict.fromkeys(m.lower() for m in re.findall(rf"\b(?:{PII_OBJECTS})\b", q, re.I)))
        return f"Refused: direct personal details ({asked}) aren't available through Ask."
    if m := MARKETING_USE.search(q):
        return f"Refused: collections data can't be used for marketing or cross-selling (asked: '{m.group(0)}')."
    if m := CREDIT_DECISION.search(q):
        return f"Refused: credit decisions and limit changes are not an allowed use of collections data (asked: '{m.group(0)}')."
    if ACTION_REQUEST.search(q):
        return ("Refused: Ask answers questions; it can't contact customers or change cases. Use the queue and the "
                "next best action card, where a person approves each action.")
    if m := WRITE_REQUEST.search(q):
        return f"Refused: Ask is read-only, so it can't {m.group(2).lower()} data."
    if tokens is not None and tokens.out_of_scope:
        return f"Refused: '{tokens.out_of_scope}' is outside the data you're allowed to query."
    return None
