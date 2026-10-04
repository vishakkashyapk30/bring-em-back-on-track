# ruff: noqa: E501
"""Grounded answers from what was said and written about a customer: agent notes, call transcripts and the speech-to-text
of the recordings (index: rag/search_index.py, built by `python -m rag.ingest`).

    search(question, scope, *, case_id=None, golden_id=None, k=8, sources=("note", "transcript", "voice")) -> list[dict]
    answer(question, scope, *, case_id=None, golden_id=None, k=8) -> dict

Access is decided first: `scope` (common.ask_scope.AskScope, None for batch jobs) says which cases a person may read through
`scope.case_allowed`; an agent gets only their own cases, a team lead their team's, analysts nothing (aggregates only).
Text is redacted when the index is built (PII patterns, names, protected grounds), so nothing sensitive is stored to return.

An answer always carries citations, and a citation is always a retrieved snippet with a quote that appears word for word in
it. No valid citation, no answer: the question is refused. Offline the answer is extractive (the best sentences, quoted);
with a language model the model writes the wording and the same checks decide whether it is shown, else the extractive
answer is used (`by_llm` says which).
"""

from __future__ import annotations

import re
from datetime import datetime

from common.ask_scope import AskScope
from llm.providers.offline import register
from rag import search_index as si

SOURCES = ("note", "transcript", "voice")
NOTHING = "Nothing in the notes or calls says that."
GENERIC = frozenset("""customer cust client borrower person call calls said say says tell told mention mentioned mentions
    speak spoke talk talked last latest recent recently previous first ever time times interaction interactions contact
    contacts conversation conversations note notes part quote summarise summarize summary give show find please
    anything something about regarding record recording recordings transcript three two four five few raise raised make made want wanted get got""".split())
GENERIC = frozenset(si.stem(w) for w in GENERIC)
# Words a customer or note might use instead (stemmed). Groups are matched as a whole for relevance.
SYNONYMS_RAW: dict[str, list[str]] = {
    "hardship": ["hardship", "laid", "job", "reduced", "income", "tight", "struggling", "sick", "medical", "financial",
                 "difficult", "difficulté", "disability", "flood", "evacuated", "separation", "unemployed"],
    "dispute": ["dispute", "charge", "fraud", "wrong", "mine", "authorized", "authorised", "contest", "conteste",
                "statement", "applied"],
    "promise": ["promise", "ptp", "promesse", "commit", "pay"],
    "promised": ["promise", "ptp", "promesse", "commit", "pay"],
    "pay": ["pay", "pmt", "payment", "paiement", "payer"],
    "payment": ["payment", "pmt", "pay", "paiement", "payer"],
    "fee": ["fee", "frais", "charge"],
    "late": ["late", "retard"],
    "complain": ["complain", "complaint", "plainte"], "complaint": ["complaint", "complain", "plainte"],
    "stop": ["stop", "cease", "arrêtez", "harassment"],
    "forgot": ["forgot", "forget", "oublié"],
    "bankruptcy": ["bankruptcy", "proposal", "trustee", "insolvency"],
    "callback": ["callback", "cb", "rappel"],
}
for _w in ("struggling", "struggle", "financially", "financial", "afford", "broke", "difficulty"):
    SYNONYMS_RAW[_w] = [_w, *SYNONYMS_RAW["hardship"]]
SYNONYMS: dict[str, list[str]] = {si.stem(k): [si.stem(w) for w in v] for k, v in SYNONYMS_RAW.items()}
RECENT = re.compile(r"\b(last|latest|most recent|recent(ly)?|previous)\b", re.I)
SUMMARY = re.compile(r"\b(summari[sz]e|summary|recap|overview)\b.*\b(interactions?|contacts?|calls?|conversations?|notes?)\b|"
                     r"\b(last|latest|recent|previous)\b.*\b(interactions?|contacts?|conversations?)\b", re.I)
NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "a few": 3, "few": 3}
CUSTOMER_VOICE = re.compile(r"\b(customer|client|cust|they|he|she)\b.{0,40}\b(say|said|says|mention|told|tell|promis|claim|state|ask|"
                            r"agree|refus|dispute|complain|blame|explain|report)", re.I)
PROMISE = re.compile(r"\b(promis\w*|ptp|commit\w* to pay|agree\w* to pay)\b", re.I)
SCOPE_FILTERED = ("agent", "team_lead")


def _iso(ts) -> str | None:
    return None if ts is None or str(ts) == "NaT" else ts.isoformat() if hasattr(ts, "isoformat") else str(ts)


def _label(r: dict) -> str:
    ts = r.get("ts")
    try:
        when = datetime.fromisoformat(str(ts)).strftime("%-d %b %Y") if ts else "unknown date"
    except ValueError:
        when = str(ts)
    if r["source"] == "note":
        return f"Agent note on {when}"
    who = f" ({r['speaker']})" if r.get("speaker") else ""
    return f"{'Call' if r['source'] == 'transcript' else 'Recording'} on {when}, turn {r['turn_index']}{who}"


def _summary_count(question: str) -> int:
    for w, n in NUMBER_WORDS.items():
        if re.search(rf"\b{w}\b", question, re.I):
            return n
    m = re.search(r"\b(\d+)\b", question)
    return min(int(m.group(1)), 10) if m else 3


# ------------------------------------------------------------------ planning

def plan(question: str) -> dict:
    """Terms (stemmed, grouped with their synonyms), plus the question's intent."""
    raw = [t for t in si.tokenize(question) if t not in GENERIC and not t.isdigit()]
    groups: list[list[str]] = []
    for t in dict.fromkeys(raw):
        groups.append(list(dict.fromkeys([t, *SYNONYMS.get(t, [])])))
    # "late fee" style phrases keep their own words; "or" lets either group count
    return {"groups": groups, "any": bool(re.search(r"\bor\b", question, re.I)) and len(groups) > 1,
            "summary": bool(SUMMARY.search(question)), "promise": bool(PROMISE.search(question)),
            "system": bool(re.search(r"\b(system|kept|broken|status|outcome)\b", question, re.I)), "recent": bool(RECENT.search(question)),
            "customer": bool(CUSTOMER_VOICE.search(question)), "n": _summary_count(question)}


_vocab: dict[str, dict[str, int]] = {}


def _near(a: str, b: str) -> bool:
    """Edit distance 1 (insert, delete, substitute) or one adjacent swap: the notes are full of typing slips."""
    if a == b or abs(len(a) - len(b)) > 1 or a[0] != b[0]:
        return False
    if len(a) == len(b):
        d = [i for i in range(len(a)) if a[i] != b[i]]
        return len(d) == 1 or (len(d) == 2 and d[1] == d[0] + 1 and a[d[0]] == b[d[1]] and a[d[1]] == b[d[0]])
    s_, l_ = sorted((a, b), key=len)
    return any(l_[:i] + l_[i + 1:] == s_ for i in range(len(l_)))


def add_typos(con, groups: list[list[str]]) -> list[list[str]]:
    """Each key term also matches its rarer one-slip spellings found in the index vocabulary."""
    key = f"{si.path()}:{si.path().stat().st_mtime}"
    if key not in _vocab:
        _vocab.clear()
        _vocab[key] = dict(con.execute("SELECT term, df FROM terms").fetchall())
    vocab = _vocab[key]
    out = []
    for g in groups:
        base = g[0]
        extra = [t for t, df in vocab.items() if len(base) >= 5 and _near(base, t) and df < vocab.get(base, 10**9)] \
            if base in vocab or len(base) >= 5 else []
        out.append(list(dict.fromkeys([*g, *extra])))
    return out


def _weights(groups: list[list[str]]) -> dict[str, float]:
    w: dict[str, float] = {}
    for g in groups:
        for i, t in enumerate(g):
            w[t] = max(w.get(t, 0.0), 1.0 if i == 0 else 0.6)
    return w


def _relevant(text: str, groups: list[list[str]], any_group: bool, idf: dict[str, float]) -> bool:
    """The snippet must cover enough of the question's key terms (a term nobody ever wrote counts as uncovered)."""
    if not groups:
        return False
    toks = set(si.tokenize(text))
    top = max(idf.values(), default=1.0)
    total = got = 0.0
    hit = False
    for g in groups:
        wt = idf.get(g[0], top)
        total += wt
        if toks & set(g):
            got += wt
            hit = True
    return hit if any_group else got / total >= 0.5


# ------------------------------------------------------------------ search

def _allowed_cases(scope: AskScope | None, case_id: str | None, golden_id: str | None, con) -> set[str] | None:
    """None = no restriction; otherwise the cases that may be read. Checked before any text is retrieved."""
    if case_id:
        return {case_id} if scope is None or scope.case_allowed is None or scope.case_allowed(case_id) else set()
    if golden_id:
        cases = [r[0] for r in con.execute("SELECT DISTINCT case_id FROM interactions WHERE golden_id = ?", [golden_id]).fetchall()]
        if scope is None or scope.case_allowed is None:
            return set(cases)
        return {c for c in cases if scope.case_allowed(c)}
    return None


def search(question: str, scope: AskScope | None, *, case_id: str | None = None, golden_id: str | None = None, k: int = 8,
           sources: tuple[str, ...] = SOURCES) -> list[dict]:
    """Snippets {source, doc_id, case_id, contact_id, ts, speaker, turn_index, text, score, label, golden_id, call_key}
    ranked by BM25 over the redacted text, only from cases `scope` may read. Questions with no evidence return []."""
    if not si.available():
        return []
    if scope is not None and scope.case_allowed is None and scope.role in ("analyst",):
        return []
    con = si.connect()
    try:
        allowed = _allowed_cases(scope, case_id, golden_id, con)
        if allowed is not None and not allowed:
            return []
        p = plan(question)
        p["groups"] = add_typos(con, p["groups"])
        src = [s for s in sources if s in SOURCES]
        where, params = ["source IN (SELECT unnest(?))"], [src]
        if allowed is not None:
            where.append("case_id IN (SELECT unnest(?))")
            params.append(sorted(allowed))
        scoped_free = allowed is None and scope is not None and scope.case_allowed is not None
        if p["summary"] and allowed is not None:
            rows = _recent_docs(con, " AND ".join(where), params, p["n"], src)
        else:
            if not p["system"]:
                where.append("speaker <> 'system'")
            if p["customer"]:
                where.append("(source = 'note' OR speaker NOT IN ('agent', 'ivr', 'system'))")
            rows = si.bm25(con, _weights(p["groups"]), where=" AND ".join(where), params=params,
                           limit=600 if scoped_free else 60)
            terms = [g[0] for g in p["groups"]]
            idf = _idf(con, terms)
            rows = [r for r in rows if _relevant(r["text"], p["groups"], p["any"], idf)]
            if p["promise"]:  # a promise names an amount or a date, or says "promise" outright
                rows = [r for r in rows if re.search(r"\d|promis|ptp|promesse", r["text"], re.I)]
            if p["recent"] and rows:
                top = rows[0]["score"]
                rows = sorted([r for r in rows if r["score"] >= 0.4 * top], key=lambda r: (str(r["ts"]), r["score"]), reverse=True)
        memo: dict[str, bool] = {}
        out = []
        for r in rows:
            if scoped_free:
                c = r["case_id"]
                if c not in memo:
                    memo[c] = bool(scope.case_allowed(c))
                if not memo[c]:
                    continue
            r["ts"] = _iso(r["ts"])
            r["label"] = _label(r)
            out.append(r)
            if len(out) >= (max(k, 40) if p["summary"] else k):
                break
        return out
    finally:
        con.close()


def _idf(con, terms: list[str]) -> dict[str, float]:
    import math

    n, _ = si.stats(con)
    df = si.term_df(con, terms)
    return {t: math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5)) for t in terms if t in df}


def _recent_docs(con, where: str, params: list, n: int, src: list[str]) -> list[dict]:
    """Every turn of the last n interactions (a call counts once, even when it is also a recording)."""
    docs = con.execute(f"""SELECT call_key_or_doc, max(ts) AS ts FROM (
                               SELECT coalesce(call_key, doc_id) AS call_key_or_doc, ts, source FROM interactions WHERE {where})
                           GROUP BY 1 ORDER BY 2 DESC LIMIT {int(n)}""", params).fetchall()
    keys = [d[0] for d in docs]
    if not keys:
        return []
    rows = con.execute(f"""SELECT *, 1.0 AS score FROM interactions WHERE {where} AND coalesce(call_key, doc_id) IN (SELECT unnest(?))
                           ORDER BY ts DESC, source, doc_id, turn_index""", [*params, keys]).df().to_dict("records")
    seen: dict[str, str] = {}
    out, per_call = [], {}
    for r in rows:  # one source per call: prefer the released transcript over the recording's speech-to-text
        key = r["call_key"] or r["doc_id"]
        rank = {"transcript": 0, "note": 0, "voice": 1}[r["source"]]
        if key in seen and seen[key] != r["source"] and rank:
            continue
        seen.setdefault(key, r["source"])
        out.append(r)
        per_call.setdefault(key, []).append(r)
    keep: set[int] = set()
    for rs in per_call.values():
        if rs[0]["source"] == "note":
            keep |= {id(r) for r in rs}
            continue
        cust = [r for r in rs if r["speaker"] == "customer"] or rs
        best = sorted(cust, key=lambda r: -len(r["text"]))[:3]  # the most informative customer lines, in call order
        keep |= {id(r) for r in best}
    return [r for r in out if id(r) in keep]


# ------------------------------------------------------------------ answering

def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?;])\s+|\n+", text) if s.strip()]


def _best_quote(text: str, groups: list[list[str]], limit: int = 220, digits: bool = False) -> str:
    sents = _sentences(text) or [text.strip()]
    terms = {t for g in groups for t in g}
    best = max(sents, key=lambda s: (digits and bool(re.search(r"\d", s)), len(terms & set(si.tokenize(s))), -len(s)))
    return best if len(best) <= limit else best[:limit].rsplit(" ", 1)[0]


def _cite(r: dict, quote: str) -> dict:
    return {"source": r["source"], "doc_id": r["doc_id"], "case_id": r.get("case_id"), "contact_id": r.get("contact_id"),
            "turn_index": int(r["turn_index"]), "ts": r.get("ts"), "speaker": r.get("speaker"), "quote": quote,
            "label": r.get("label") or _label(r), "section": "note" if r["source"] == "note" else f"turn {int(r['turn_index'])}"}


def _refusal(reason: str = NOTHING) -> dict:
    return {"answer": None, "citations": [], "refused": True, "refusal_reason": reason, "by_llm": False}


def extractive(question: str, snippets: list[dict]) -> dict:
    """Offline answer: the most relevant sentences, each quoted with its source. Nothing relevant: refuse."""
    if not snippets:
        return _refusal()
    p = plan(question)
    lines, cites, seen = [], [], set()
    if p["summary"]:
        by_doc: dict[str, list[dict]] = {}
        for r in snippets:
            by_doc.setdefault(r["call_key"] or r["doc_id"] if r["source"] != "note" else r["doc_id"], []).append(r)
        for rs in list(by_doc.values())[:p["n"]]:
            cust = [r for r in rs if r["speaker"] == "customer"] or rs
            pick = sorted(sorted(cust, key=lambda r: -len(r["text"]))[:2], key=lambda r: r["turn_index"])
            for r in pick:
                q = _best_quote(r["text"], [])
                cites.append(_cite(r, q))
            lines.append(f"{cites[-len(pick)]['label'].split(',')[0]}: " + " ".join(f"\"{c['quote']}\"" for c in cites[-len(pick):]))
    else:
        for r in snippets:
            q = _best_quote(r["text"], p["groups"], digits=p["promise"])
            if (r["doc_id"], r["turn_index"]) in seen:
                continue
            seen.add((r["doc_id"], r["turn_index"]))
            cites.append(_cite(r, q))
            if len(cites) == 3:
                break
        lines = [f"{c['label']}: \"{c['quote']}\"" for c in cites]
    if not cites:
        return _refusal()
    return {"answer": " ".join(lines), "citations": cites, "refused": False, "refusal_reason": None, "by_llm": False}


@register("interaction_answer")
def answer_offline(inputs: dict) -> dict:
    """Offline handler for the prompt: the extractive answer, in the model's output shape (ref, doc_id, turn_index, quote)."""
    snips = [dict(s, call_key=s.get("call_key"), score=1.0) for s in inputs.get("snippets", [])]
    out = extractive(inputs["question"], snips)
    refs = {(s["doc_id"], s["turn_index"]): s.get("ref") for s in snips}
    return {"answer": out["answer"], "refused": out["refused"], "refusal_reason": out["refusal_reason"],
            "citations": [{"ref": refs.get((c["doc_id"], c["turn_index"]), ""), "doc_id": c["doc_id"],
                           "turn_index": c["turn_index"], "quote": c["quote"]} for c in out["citations"]]}


def _numbers(t: str) -> set[str]:
    return {n.replace(",", "") for n in re.findall(r"\d+(?:[.,]\d+)*", t)}


def validate(out: dict, snippets: list[dict]) -> list[dict] | None:
    """The model's citations as full citation records, or None when anything is ungrounded: unknown snippet, quote not
    word for word in it, no citation at all, or a number in the answer that no cited quote (or cited date) contains."""
    cites = out.get("citations") or []
    if out.get("refused") or not out.get("answer") or not cites:
        return None
    by_ref = {s["ref"]: s for s in snippets}
    by_key = {(s["doc_id"], int(s["turn_index"])): s for s in snippets}
    full = []
    for c in cites:
        s = by_ref.get(c.get("ref")) or by_key.get((c.get("doc_id"), int(c.get("turn_index", -1) or -1)))
        quote = (c.get("quote") or "").strip()
        if s is None or not _norm(quote) or _norm(quote) not in _norm(s["text"]):
            return None
        full.append(_cite(s, quote))
    allowed = set()
    for c in full:
        allowed |= _numbers(c["quote"]) | _numbers(c["label"])
        allowed |= _numbers(str(c["ts"] or ""))
    if _numbers(out["answer"]) - allowed - {str(i) for i in range(1, 11)} :
        return None
    return full


def answer(question: str, scope: AskScope | None, *, case_id: str | None = None, golden_id: str | None = None,
           k: int = 8) -> dict:
    """{answer, citations:[{source, doc_id, case_id, contact_id, turn_index, ts, speaker, quote, label, section}], refused,
    refusal_reason, by_llm}. Never an answer without a valid citation."""
    from common.llm_mode import effective_provider

    if scope is not None and scope.case_allowed is not None and case_id and not scope.case_allowed(case_id):
        return _refusal(scope.case_denied_reason)
    snippets = search(question, scope, case_id=case_id, golden_id=golden_id, k=k)
    if not snippets:
        if scope is not None and scope.role == "analyst":
            return _refusal("Refused: analysts see aggregates only, not an individual customer's notes or calls.")
        return _refusal()
    base = extractive(question, snippets)
    if effective_provider() == "offline" or base["refused"]:
        return base
    for i, s in enumerate(snippets, 1):
        s["ref"] = f"S{i}"
    try:
        from llm.client import complete_json

        out = complete_json("interaction_answer", 1, {
            "question": question,
            "snippets": [{"ref": s["ref"], "doc_id": s["doc_id"], "turn_index": int(s["turn_index"]), "label": s["label"],
                          "speaker": s["speaker"], "text": s["text"]} for s in snippets]}, "interaction_answer")
    except Exception:  # noqa: BLE001 - a model problem must never break the answer
        return base
    if out.get("_meta", {}).get("provider") == "offline":
        return base
    if out.get("refused"):
        return _refusal(out.get("refusal_reason") or NOTHING)
    cites = validate(out, snippets)
    if cites is None:
        return base
    return {"answer": out["answer"].strip(), "citations": cites, "refused": False, "refusal_reason": None, "by_llm": True}
