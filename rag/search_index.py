# ruff: noqa: E501
"""Search index over what people and systems actually said: agent notes, call transcripts and the speech-to-text of the
voice recordings. A separate DuckDB file (`data/search.duckdb`), never the warehouse: the API only ever reads it, and
`python -m rag.ingest` rebuilds it from the warehouse, the released transcript files and `voice_turns.parquet`.

Only redacted text goes in. Notes are redacted with `llm/redact.py` (the same patterns, run inside DuckDB); transcripts
come pre-redacted from the release and pass through the same patterns again; notes whose redaction is still
`needs_review` are left out. Protected attributes are never columns here.

Ranking is BM25 over an inverted index kept in plain DuckDB tables (no extension to install, so it also works offline
and inside the container). Tables:
  interactions(uid, source, doc_id, case_id, golden_id, contact_id, call_key, ts, speaker, turn_index, note_type, text)
  postings(term, uid, tf)          one row per term and interaction, sorted by term
  terms(term, df)                  document frequency
  docs(uid, len)                   token count
  meta(key, value)                 counts, average length, build time
"""

from __future__ import annotations

import json
import logging
import math
import re
import time
from pathlib import Path

import duckdb
import pandas as pd

from common.config import get_settings
from llm.redact import _PATTERNS

log = logging.getLogger("search_index")
K1, B = 1.2, 0.75
WORD = re.compile(r"[a-z0-9àâçéèêëîïôûùüÿœ']+")
STOP = frozenset(
    "a an and are as at be been but by can did do does for from had has have he her his i if in into is it its me my of "
    "on or our she so that the their them then there they this to us was we were what when where which who why will with "
    "you your about any how not no yes just also than too very".split())


def path() -> Path:
    return get_settings().data_dir / "search.duckdb"


def stem(t: str) -> str:
    """Light, rule-based normalisation applied to documents and questions alike (plurals, -ing, -ed, final e)."""
    t = t.strip("'")
    if t.endswith("'s"):
        t = t[:-2]
    if len(t) > 5 and t.endswith("ies"):
        t = t[:-3] + "y"
    elif len(t) > 6 and t.endswith("ing"):
        t = t[:-3]
    elif len(t) > 5 and t.endswith("ed"):
        t = t[:-2]
    elif len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
        t = t[:-1]
    if len(t) > 4 and t.endswith("e"):
        t = t[:-1]
    return t


def tokenize(text: str) -> list[str]:
    return [stem(w) for w in WORD.findall(text.lower()) if w not in STOP]


def _sql_stem(col: str) -> str:
    """The same normalisation as `stem`, as a DuckDB expression (for the plain words of the unnested text)."""
    inner = (f"CASE WHEN length({col})>5 AND {col} LIKE '%ies' THEN left({col},length({col})-3)||'y' "
             f"WHEN length({col})>6 AND {col} LIKE '%ing' THEN left({col},length({col})-3) "
             f"WHEN length({col})>5 AND {col} LIKE '%ed' THEN left({col},length({col})-2) "
             f"WHEN length({col})>3 AND {col} LIKE '%s' AND {col} NOT LIKE '%ss' THEN left({col},length({col})-1) "
             f"ELSE {col} END")
    return f"CASE WHEN length({inner})>4 AND ({inner}) LIKE '%e' THEN left({inner},length({inner})-1) ELSE {inner} END"


def _sql_redact(col: str) -> str:
    """llm/redact.py's patterns as nested regexp_replace calls (RE2 accepts them as they are)."""
    expr = col
    for token, pat in _PATTERNS:
        flags = "gi" if pat.flags & re.I else "g"
        expr = f"regexp_replace({expr}, '{pat.pattern}', '{token}', '{flags}')"
    return expr


# Clauses that mention a protected or sensitive ground are replaced, never returned (plan.md section 5, the notes carry
# religion, pregnancy and similar remarks). Typo-tolerant because the notes contain typos. Clauses split on , . ; and " - ".
PROTECTED_CLAUSE = (
    r"(?i)[^.;,\n]*(\brelig|\bchurch|\bchurh|\bchruch|\bcuhrch|\bmosque|\btemple|\bsynagogue|\bpray|\bpregn|\bprgen|"
    r"\bethnic|\bracial|\brace\b|\bcitizen|\bimmigra|\bnewcomer|\brefugee|\bwork permit|\bgender|\btransgender|\bgay\b|"
    r"\blesbian|\blgbt|\bsexual orientation|\bmarital|\bmarried|\bwidow|"
    r"mention\w* (the\w* |thi\w* |tei?r |th?ier )?r\w{3,6}\b|attend\w* c\w{3,5}h? on s\w+|\bb\w{2,5} p\w{5,8}\b)[^.;,\n]*")
SPEAK_NAME = r"([Ss]peak(?:ing)? (?:with|to)|[Mm]essage is for|[Aa]sk(?:ing)? for|[Ss]poke (?:with|to)) (?:(?:Mr|Ms|Mrs|Dr)\.? )?[A-Z][a-z'\-]+(?: [A-Z][a-z'\-]+)?"


def _sql_clean(col: str) -> str:
    """Clause scrub for protected grounds, then PII patterns, then names after 'May I speak with ...'."""
    x = f"regexp_replace({col}, ' - ', '; ', 'g')"
    x = f"regexp_replace({x}, '{PROTECTED_CLAUSE.replace(chr(39), chr(39) * 2)}', '[protected detail removed]', 'g')"
    x = _sql_redact(x)
    return f"regexp_replace({x}, '{SPEAK_NAME.replace(chr(39), chr(39) * 2)}', '\\1 [NAME]', 'g')"


def connect(read_only: bool = True) -> duckdb.DuckDBPyConnection:
    if read_only and not path().exists():
        raise FileNotFoundError(f"{path()} not built yet; run `python -m rag.ingest`")
    return duckdb.connect(str(path()), read_only=read_only)


def available() -> bool:
    return path().exists()


# ---------------------------------------------------------------- build

def _files() -> Path:
    return get_settings().release_dir / "files"


def _transcript_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    """(call headers, turns) for every released transcript."""
    from common.db import warehouse

    con = warehouse()
    try:
        con.execute("SET search_path='silver,gold'")
        hdr = con.execute("""SELECT t.transcript_id, t.contact_id, t.case_id, c.golden_id, t.call_start_ts AS ts,
                                    t.file_path, t.voice_sample_id
                             FROM call_transcripts t LEFT JOIN c360_case c USING (case_id)""").df()
    finally:
        con.close()
    rows = []
    for r in hdr.itertuples():
        p = _files() / r.file_path
        try:
            turns = json.loads(p.read_text())["turns"]
        except (OSError, KeyError, json.JSONDecodeError):
            continue
        for t in turns:
            if (t.get("text") or "").strip():
                rows.append((r.transcript_id, int(t["turn_index"]), t["speaker"], t["text"]))
    return hdr, pd.DataFrame(rows, columns=["transcript_id", "turn_index", "speaker", "text"])


def build_inverted(out: duckdb.DuckDBPyConnection) -> None:
    """tok, docs, postings and terms from the `interactions` table (also used by the unit tests on a tiny index)."""
    out.execute(f"""CREATE TABLE tok AS
        SELECT uid, {_sql_stem('w2')} AS term FROM (
            SELECT uid, regexp_replace(regexp_replace(w, '^''+|''+$', '', 'g'), '''s$', '') AS w2 FROM (
                SELECT uid, unnest(regexp_extract_all(lower(text), '[a-z0-9àâçéèêëîïôûùüÿœ'']+')) AS w FROM interactions)
            WHERE w NOT IN ({', '.join(repr(x) for x in sorted(STOP))}))
        WHERE length(w2) > 0""")
    out.execute("CREATE TABLE docs AS SELECT uid, count(*)::INTEGER AS len FROM tok GROUP BY uid")
    out.execute("CREATE TABLE postings AS SELECT term, uid, count(*)::INTEGER AS tf FROM tok "
                "GROUP BY term, uid ORDER BY term, uid")
    out.execute("DROP TABLE tok")
    out.execute("CREATE TABLE terms AS SELECT term, count(*)::BIGINT AS df FROM postings GROUP BY term")


def build(verbose: bool = True) -> dict:
    """Rebuild data/search.duckdb from scratch (written to a temp file, then swapped in)."""
    from common.db import warehouse
    from features.voice import VOICE_TURN_COLS  # noqa: F401  (documents the parquet layout)

    t0 = time.time()
    s = get_settings()
    tmp = path().with_suffix(".building")
    for f in (tmp, Path(str(tmp) + ".wal")):
        f.unlink(missing_ok=True)
    out = duckdb.connect(str(tmp))
    out.execute("PRAGMA threads=8")

    def say(msg: str) -> None:
        if verbose:
            print(f"[{time.time() - t0:6.1f}s] {msg}", flush=True)

    # 1. agent notes (read through the shared read-only warehouse connection; redaction runs inside DuckDB)
    wh = warehouse()
    try:
        wh.execute("SET search_path='silver,gold'")
        notes = wh.execute("""SELECT n.note_id, n.case_id, c.golden_id, n.contact_id, n.note_ts AS ts, n.note_source, n.note_type,
                                     n.note_text
                              FROM agent_notes n LEFT JOIN c360_case c ON c.case_id = n.case_id
                              WHERE n.note_text IS NOT NULL AND trim(n.note_text) <> '' AND n.redaction_status <> 'needs_review'
                           """).df()
    finally:
        wh.close()
    out.register("notes_df", notes)
    out.execute(f"""CREATE TABLE stage AS
        SELECT 'note' AS source, note_id AS doc_id, case_id, golden_id, contact_id, NULL::VARCHAR AS call_key, ts,
               CASE WHEN note_source = 'auto_system' THEN 'system' ELSE 'agent' END AS speaker, 1 AS turn_index, note_type,
               trim({_sql_clean('note_text')}) AS text
        FROM notes_df""")
    del notes
    n_notes = out.execute("SELECT count(*) FROM stage").fetchone()[0]
    say(f"notes: {n_notes:,}")

    # 2. released call transcripts (turn level)
    hdr, turns = _transcript_frames()
    tr = turns.merge(hdr[["transcript_id", "contact_id", "case_id", "golden_id", "ts"]], on="transcript_id")
    tr = tr.assign(source="transcript", doc_id=tr.transcript_id, call_key=tr.transcript_id, note_type=None)
    out.register("tr_df", tr)
    out.execute(f"""INSERT INTO stage SELECT source, doc_id, case_id, golden_id, contact_id, call_key, ts, speaker,
                           turn_index, note_type, trim({_sql_clean('text')}) FROM tr_df""")
    n_tr = len(tr)
    say(f"transcript turns: {n_tr:,} from {tr.transcript_id.nunique():,} calls")

    # 3. speech-to-text of the recordings (written by `python -m features.voice transcribe`)
    n_voice = 0
    vp = s.features_dir / "voice_turns.parquet"
    if vp.exists():
        vt = pd.read_parquet(vp)
        vt = vt[vt.text.fillna("").str.strip() != ""]
        h = hdr[hdr.voice_sample_id.notna()].rename(columns={"voice_sample_id": "vs"})
        v = vt.merge(h[["vs", "transcript_id", "case_id", "golden_id", "ts"]], left_on="voice_sample_id", right_on="vs")
        v = v.assign(source="voice", doc_id=v.voice_sample_id, call_key=v.transcript_id, note_type=None)
        out.register("v_df", v)
        out.execute(f"""INSERT INTO stage SELECT source, doc_id, case_id, golden_id, contact_id, call_key, ts, speaker,
                               turn_index, note_type, trim({_sql_clean('text')}) FROM v_df""")
        n_voice = len(v)
        say(f"voice turns: {n_voice:,} from {v.voice_sample_id.nunique():,} recordings")
    else:
        say("voice turns: none (run `python -m features.voice transcribe --n 2000` first)")

    # 4. final table, ordered by case so a case's interactions sit together
    out.execute("""CREATE TABLE interactions AS
        SELECT row_number() OVER (ORDER BY case_id, ts, source, doc_id, turn_index)::BIGINT AS uid, *
        FROM stage WHERE text <> '' ORDER BY uid""")
    out.execute("DROP TABLE stage")
    say("interactions table built")

    # 5. inverted index
    build_inverted(out)
    say("inverted index built")

    n, avg = out.execute("SELECT count(*), avg(len) FROM docs").fetchone()
    meta = {"interactions": n, "notes": n_notes, "transcript_turns": n_tr, "voice_turns": n_voice,
            "avg_len": float(avg), "terms": out.execute("SELECT count(*) FROM terms").fetchone()[0],
            "postings": out.execute("SELECT count(*) FROM postings").fetchone()[0],
            "built_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    out.execute("CREATE TABLE meta(key VARCHAR, value VARCHAR)")
    out.executemany("INSERT INTO meta VALUES (?, ?)", [(k, str(v)) for k, v in meta.items()])
    out.execute("CHECKPOINT")
    out.close()
    for f in (path(), Path(str(path()) + ".wal")):
        f.unlink(missing_ok=True)
    tmp.rename(path())
    meta["seconds"] = round(time.time() - t0, 1)
    meta["size_mb"] = round(path().stat().st_size / 1e6, 1)
    say(f"done: {meta}")
    return meta


# ---------------------------------------------------------------- query

_stats: dict[str, tuple[int, float]] = {}


def stats(con: duckdb.DuckDBPyConnection) -> tuple[int, float]:
    key = f"{path()}:{path().stat().st_mtime}"
    if key not in _stats:
        n, avg = con.execute("SELECT count(*), avg(len) FROM docs").fetchone()
        _stats.clear()
        _stats[key] = (int(n), float(avg))
    return _stats[key]


def term_df(con: duckdb.DuckDBPyConnection, terms: list[str]) -> dict[str, int]:
    if not terms:
        return {}
    return dict(con.execute("SELECT term, df FROM terms WHERE term IN (SELECT unnest(?))", [terms]).fetchall())


def bm25(con: duckdb.DuckDBPyConnection, weights: dict[str, float], *, where: str = "TRUE", params: list | None = None,
         limit: int = 50) -> list[dict]:
    """Top interactions by BM25 for weighted query terms; `where` filters the interactions table (alias i)."""
    if not weights:
        return []
    n, avg = stats(con)
    df = term_df(con, list(weights))
    usable = {t: w * max(0.0, math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))) for t, w in weights.items()
              if t in df}
    if not usable:
        return []
    q = pd.DataFrame({"term": list(usable), "w": list(usable.values())})
    con.register("q_terms", q)
    try:
        sql = f"""
            SELECT i.*, s.score FROM (
                SELECT p.uid, sum(q.w * p.tf * ({K1} + 1) / (p.tf + {K1} * (1 - {B} + {B} * d.len / {avg}))) AS score
                FROM postings p JOIN q_terms q USING (term) JOIN docs d USING (uid)
                WHERE p.uid IN (SELECT uid FROM interactions i WHERE {where})
                GROUP BY p.uid ORDER BY score DESC LIMIT {int(limit)}) s
            JOIN interactions i USING (uid) ORDER BY s.score DESC, i.ts DESC"""
        return con.execute(sql, params or []).df().to_dict("records")
    finally:
        con.unregister("q_terms")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(build(), indent=2, default=str))
