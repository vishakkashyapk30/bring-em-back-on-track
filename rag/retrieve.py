"""BM25 retrieval over current policy sections, with document precedence (D12).

Only current versions are indexed (superseded_by IS NULL). Among sections scoring close to the best, the higher
authority wins (regulatory summary > policy > programme terms > procedure > call script > FAQ), so an outdated
FAQ answer never beats the policy. French questions search the French documents first.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from functools import lru_cache

from rag.index import Section, load_sections

STOP = set("""a an the of to in on for and or is are be can we our do does what how long much many which who when
why with by at as it this that those these any all from into about there their them your you i me my customer
customers agent""".split())
FR_HINT = re.compile(r"\b(le|la|les|des|est|une|pour|avec|quand|combien|peut|doit)\b", re.I)
SYNONYMS = {"attempts": ["calls", "contact"], "sue": ["legal", "court", "lawsuit", "litigation"],
            "proposal": ["insolvency", "bankruptcy"], "grace": ["broken", "promise"],
            "hours": ["shifts", "hardship", "reduced"], "mid": ["mid-stage"], "dnc": ["do", "not", "call"],
            "programme": ["program"], "program": ["programme"], "drop": ["outage", "degraded", "incident"],
            "volume": ["capacity"],
            # everyday wording the policy documents don't use
            "stop": ["cease", "communication"], "stopping": ["cease", "communication"], "contacting": ["contact", "communication"],
            "representative": ["represents", "lawyer", "trustee", "counselling"], "attorney": ["lawyer"],
            "counsellor": ["counselling"], "counselor": ["counselling"], "bankrupt": ["bankruptcy", "insolvency"],
            "bankruptcy": ["insolvency", "stay"], "layoff": ["hardship"], "laid": ["hardship"], "fired": ["hardship"],
            "unemployed": ["hardship"], "jobless": ["hardship"], "job": ["hardship", "income"], "sick": ["hardship"],
            "illness": ["hardship"], "text": ["sms"], "texts": ["sms"], "cap": ["maximum"], "limit": ["maximum"],
            "holiday": ["holidays", "statutory"]}


def _stem(t: str) -> str:
    return t[:-1] if len(t) > 3 and t.endswith("s") and not t.endswith("ss") else t


def tokens(text: str) -> list[str]:
    return [_stem(t) for t in re.findall(r"[a-zà-ÿ0-9§]+", text.lower()) if t not in STOP and (len(t) > 1 or t.isdigit())]


def idf(term: str) -> float:
    return _active().idf.get(term, 0.0)


@dataclass
class Hit:
    section: Section
    score: float


class BM25:
    def __init__(self, sections: tuple[Section, ...], k1: float = 1.4, b: float = 0.75) -> None:
        self.sections = sections
        self.docs = [tokens(f"{s.title} {s.title} {s.text}") for s in sections]  # title counted twice
        self.avgdl = sum(map(len, self.docs)) / max(len(self.docs), 1)
        df = Counter(t for d in self.docs for t in set(d))
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}
        self.tf = [Counter(d) for d in self.docs]
        self.k1, self.b = k1, b

    def score(self, q: list[str], i: int) -> float:
        tf, dl, s = self.tf[i], len(self.docs[i]), 0.0
        for t in q:
            if t in tf:
                f = tf[t]
                s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
        return s


@lru_cache
def _index() -> BM25:
    return BM25(load_sections())


# A supplied corpus (e.g. documents loaded by a test or a preview of new documents) replaces the release corpus
# for the current context only; the default index is unchanged.
_OVERRIDE: ContextVar[BM25 | None] = ContextVar("rag_corpus_override", default=None)


def _active() -> BM25:
    return _OVERRIDE.get() or _index()


@contextmanager
def use_sections(sections: Iterable[Section]) -> Iterator[None]:
    token = _OVERRIDE.set(BM25(tuple(sections)))
    try:
        yield
    finally:
        _OVERRIDE.reset(token)


def _applies(s: Section, product: str | None, province: str | None) -> bool:
    """Only documents for the right product and province (V1 §6 UC3); no filter when not given."""
    ok_product = not product or not s.products or product in s.products
    ok_province = not province or not s.provinces or "ALL" in s.provinces or province in s.provinces
    return ok_product and ok_province


def expand(question: str) -> list[str]:
    q = tokens(question)
    return q + [_stem(s) for t in list(q) for s in SYNONYMS.get(t, [])]


def retrieve(question: str, k: int = 5, language: str | None = None, product: str | None = None,
             province: str | None = None) -> list[Hit]:
    idx = _active()
    q = expand(question)
    lang = language or ("FR" if FR_HINT.search(question) and not re.search(r"\b(the|what|how)\b", question, re.I) else "EN")
    hits = [Hit(s, idx.score(q, i)) for i, s in enumerate(idx.sections)
            if s.language == lang and _applies(s, product, province)]
    hits = [h for h in hits if h.score > 0]
    hits.sort(key=lambda h: -h.score)
    if not hits:
        return []
    top = hits[0].score
    # precedence (D12): any section within 50% of the best score competes on authority first, so a policy or
    # programme-terms section beats an outdated FAQ answer on the same topic
    near = [h for h in hits if h.score >= 0.35 * top]
    rest = [h for h in hits if h.score < 0.35 * top]
    near.sort(key=lambda h: (h.section.authority, -h.score))
    return (near + rest)[:k]
