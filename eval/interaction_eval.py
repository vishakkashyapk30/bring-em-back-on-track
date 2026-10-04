# ruff: noqa: E501
"""Evaluation of grounded answers over notes, call transcripts and recordings (rag/interactions.py).

Questions are built from real cases (each has notes, released transcripts and a recording) with gold answers taken
from the structured extractors (features.transcript_features / note_features: hardship, dispute type, promise,
complaint, stop request) or from the case's own timeline. Reported: retrieval hit rate (a gold call or note among the 8
snippets), whether the answer is shown (not refused) when evidence exists, citation validity (every citation is a
retrieved snippet and its quote is word for word in it), and refusals on questions with no evidence.

    LLM_PROVIDER=offline uv run python -m eval.interaction_eval
    LLM_PROVIDER=ollama OLLAMA_MODEL=mistral:latest uv run python -m eval.interaction_eval
    LLM_PROVIDER=gemini GEMINI_API_KEY=... uv run python -m eval.interaction_eval   (one call per answered question)

Writes reports/interaction_eval_<provider>.json. Recording questions need `python -m features.voice transcribe` first.
"""

from __future__ import annotations

import argparse
import json
import random
import time
from collections import defaultdict

import pandas as pd

from common.config import get_settings
from rag import interactions as it
from rag import search_index as si

ABSENT = ["their cat", "a wedding", "a lottery win", "cryptocurrency", "a gym membership", "a tax refund", "their puppy",
          "a holiday in Spain"]


def _pool(con, n: int, seed: int) -> list[str]:
    ids = [r[0] for r in con.execute("""
        SELECT t.case_id FROM call_transcripts t
        WHERE t.voice_sample_id IS NOT NULL AND t.case_id IN (SELECT case_id FROM agent_notes)
        GROUP BY 1""").fetchall()]
    random.Random(seed).shuffle(ids)
    return ids[:n]


def _gold_tables(con, cases: list[str]) -> pd.DataFrame:
    """One row per call or note of the pool's cases with the extractor outputs and a time."""
    q = """SELECT 'transcript' AS source, f.transcript_id AS doc_id, f.case_id, t.call_start_ts AS ts, f.hardship_signal,
                  f.dispute_signal, f.dispute_type, f.complaint_cue, f.cease_request, f.ptp_amount_mentioned,
                  t.voice_sample_id
           FROM features.transcript_features f JOIN call_transcripts t USING (transcript_id)
           WHERE f.case_id IN (SELECT unnest(?))
           UNION ALL
           SELECT 'note', f.note_id, f.case_id, n.note_ts, f.hardship_signal, f.dispute_signal, f.dispute_type, f.complaint_cue,
                  f.cease_request, f.ptp_amount_mentioned, NULL
           FROM features.note_features f JOIN agent_notes n USING (note_id) WHERE f.case_id IN (SELECT unnest(?))"""
    return con.execute(q, [cases, cases]).df()


def build_questions(n_cases: int = 400, seed: int = 11) -> list[dict]:
    from common.db import warehouse

    con = warehouse()
    con.execute("SET search_path='silver,gold,features'")
    cases = _pool(con, n_cases, seed)
    g = _gold_tables(con, cases)
    # the recordings that have been transcribed (voice questions are skipped until then)
    vt = get_settings().features_dir / "voice_turns.parquet"
    have_voice = set(pd.read_parquet(vt, columns=["voice_sample_id"]).voice_sample_id) if vt.exists() else set()
    con.close()
    idx = si.connect()  # gold documents must exist in the index (blank notes and notes awaiting redaction review do not)
    present = {r[0] for r in idx.execute("SELECT DISTINCT doc_id FROM interactions WHERE case_id IN (SELECT unnest(?))",
                                         [cases]).fetchall()}
    idx.close()
    g = g[g.doc_id.isin(present)]
    by_case = {c: d for c, d in g.groupby("case_id")}
    qs: list[dict] = []

    def add(kind, question, case, gold_docs, expect_refusal=False, sources=("note", "transcript", "voice"), gold_all=None):
        qs.append({"kind": kind, "question": question, "case_id": case, "gold": sorted(gold_docs),
                   "expect_refusal": expect_refusal, "sources": list(sources), "gold_all": gold_all})

    def take(kind, n, pred, build):
        got = 0
        for c, d in by_case.items():
            if got >= n:
                break
            if c in used:
                continue
            r = build(c, d)
            if r:
                used.add(c)
                got += 1
                add(kind, *r[:2], *r[2:3], **(r[3] if len(r) > 3 else {}))
    used: set[str] = set()

    def pos(col, val_fn, question, kind, n):
        def build(c, d):
            sel = d[val_fn(d)]
            return (question, c, set(sel.doc_id)) if len(sel) else None
        take(kind, n, None, build)

    def neg(col_fn, question, kind, n):
        def build(c, d):
            return (question, c, set(), {"expect_refusal": True}) if col_fn(d) else None
        take(kind, n, None, build)

    pos("hardship", lambda d: (d.hardship_signal == "clear"), "Has the customer mentioned hardship?", "hardship", 6)
    neg(lambda d: (d.hardship_signal == "none").all(), "Has the customer mentioned hardship?", "hardship_none", 4)
    pos("dispute", lambda d: d.dispute_signal.astype(bool), "Has the customer raised a dispute?", "dispute", 4)
    neg(lambda d: (~d.dispute_signal.astype(bool)).all(), "Has the customer raised a dispute?", "dispute_none", 3)
    pos("hardship", lambda d: (d.hardship_signal == "clear"), "Is the customer struggling financially?",
        "hardship_paraphrase", 3)
    pos("dispute", lambda d: d.dispute_signal.astype(bool), "Did the customer disagree with a charge?",
        "dispute_paraphrase", 3)
    pos("late_fee", lambda d: d.dispute_type == "late_fee", "What did the customer say about the late fee?", "late_fee", 4)
    pos("not_applied", lambda d: d.dispute_type == "payment_not_applied",
        "Did the customer say a payment was not applied?", "not_applied", 2)
    pos("fraud", lambda d: d.dispute_type == "fraud", "Did the customer say the charges are fraud?", "fraud", 2)
    pos("complaint", lambda d: d.complaint_cue.astype(bool), "Did the customer want to make a complaint?", "complaint", 3)

    def promise(c, d):
        p = d[d.ptp_amount_mentioned.notna()].sort_values("ts")
        return ("When did the customer last promise to pay?", c, {p.iloc[-1].doc_id}) if len(p) >= 2 else None
    take("promise", 5, None, promise)

    def summary(c, d):
        t = d.sort_values("ts", ascending=False)
        if len(t) < 6:
            return None
        return ("Summarise the last three interactions.", c, set(t.head(3).doc_id), {"gold_all": True})
    take("summary", 4, None, summary)

    def voice(c, d):
        v = d[(d.source == "transcript") & (d.hardship_signal == "clear") & d.voice_sample_id.isin(have_voice)]
        return ("Did the customer mention hardship on the recording?", c, set(v.voice_sample_id),
                {"sources": ("voice",)}) if len(v) else None
    if have_voice:
        take("voice", 4, None, voice)

    rng = random.Random(seed)
    pool = list(by_case)
    for topic in ABSENT:
        c = rng.choice(pool)
        add("absent", f"What did the customer say about {topic}?", c, set(), expect_refusal=True)
    return qs


def _gold_hit(q: dict, snippets: list[dict]) -> bool:
    docs = {s["doc_id"] for s in snippets}
    gold = set(q["gold"])
    # a recording and its released transcript are the same call: voice_sample ids are matched through the call key
    docs |= {s["call_key"] for s in snippets if s.get("call_key")}
    return gold <= docs if q.get("gold_all") else bool(gold & docs)


def run(n_cases: int = 400, seed: int = 11, limit: int | None = None) -> dict:
    from common.llm_mode import effective_provider

    qs = build_questions(n_cases, seed)[:limit]
    rows = []
    t0 = time.time()
    for q in qs:
        kw = {"case_id": q["case_id"]}
        snippets = it.search(q["question"], None, k=8, sources=tuple(q["sources"]), **kw)
        a = it.answer(q["question"], None, k=8, **kw) if q["sources"] == ["note", "transcript", "voice"] else None
        if a is None:  # source-restricted question: answer from the restricted snippets
            a = it.extractive(q["question"], snippets) if snippets else it._refusal()
        valid = None
        if not a["refused"]:
            ids = {(s["doc_id"], int(s["turn_index"])): s for s in snippets}
            valid = bool(a["citations"]) and all(
                (c["doc_id"], c["turn_index"]) in ids and it._norm(c["quote"]) in it._norm(ids[(c["doc_id"], c["turn_index"])]["text"])
                for c in a["citations"])
        rows.append({"kind": q["kind"], "expect_refusal": q["expect_refusal"], "question": q["question"], "case_id": q["case_id"],
                     "hit": None if q["expect_refusal"] else _gold_hit(q, snippets), "refused": a["refused"],
                     "citation_valid": valid, "by_llm": a.get("by_llm", False), "answer": a["answer"]})
    df = pd.DataFrame(rows)
    pos_df, neg_df = df[~df.expect_refusal], df[df.expect_refusal]
    shown = df[~df.refused]
    by_kind = defaultdict(dict)
    for k, d in df.groupby("kind"):
        by_kind[k] = {"n": len(d), "hit": float(d.hit.mean()) if d.hit.notna().any() else None,
                      "refused": float(d.refused.mean())}
    out = {"provider": effective_provider(), "questions": len(df), "seconds": round(time.time() - t0, 1),
           "retrieval_hit_rate": round(float(pos_df.hit.mean()), 3) if len(pos_df) else None,
           "answered_when_evidence": round(float((~pos_df.refused).mean()), 3) if len(pos_df) else None,
           "citation_validity": round(float(shown.citation_valid.astype(bool).mean()), 3) if len(shown) else None,
           "refused_when_no_evidence": round(float(neg_df.refused.mean()), 3) if len(neg_df) else None,
           "answers_by_model": int(df.by_llm.sum()), "by_kind": by_kind, "rows": rows}
    p = get_settings().reports_dir / f"interaction_eval_{out['provider']}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=2, default=str))
    return out


def markdown(res: dict) -> str:
    lines = ["| Question type | n | Retrieval hit@8 | Refused |", "|---|---|---|---|"]
    for k, v in res["by_kind"].items():
        lines.append(f"| {k} | {v['n']} | {'n/a' if v['hit'] is None else format(v['hit'], '.2f')} | {v['refused']:.2f} |")
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", type=int, default=400)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    r = run(a.cases, a.seed, a.limit)
    print(markdown(r))
    print({k: v for k, v in r.items() if k not in ("rows", "by_kind")})
