"""Run every benchmark question through Ask exactly as the system is (no hand edits) and write the submission CSV
in the release template's format, then score the dev split against the gold answers.

Run: `python -m eval.run_benchmark` (or `make benchmark`). Optional: `--questions extra.csv` to append the
19:00 questions (same columns as benchmark_questions.csv).
Outputs: deliverables/benchmark_answers.csv (question_id, answer, sql_or_sources, refused) and
reports/benchmark.json (dev-split score per question).
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import time
from datetime import date
from pathlib import Path

from common.config import get_settings
from nlq.pipeline import ask

ROOT = Path(__file__).resolve().parents[1]
REL = get_settings().release_dir


def _as_of(q: dict) -> date | None:
    try:
        return date.fromisoformat(q["as_of_date"]) if q.get("as_of_date") else None
    except ValueError:
        return None


def _tol(t: str) -> float:
    m = re.search(r"([\d.]+)", t or "")
    return 0.0 if (not t or "exact" in t.lower() or not m) else float(m.group(1))


def _num(s: str) -> float | None:
    try:
        return float(str(s).replace(",", "").replace("$", "").replace("%", ""))
    except ValueError:
        return None


def score_numeric(ours: str, gold: str, tol: float) -> float:
    """Share of gold rows whose numbers match ours (row matched on its first, non-numeric key)."""
    g = list(csv.reader(gold.strip().splitlines()))
    o = list(csv.reader(ours.strip().splitlines()))
    if len(g) < 2 or len(o) < 2:
        return 0.0
    keyed = {r[0].strip().lower(): r for r in o[1:]}
    single = len(g) == 2 and len(o) == 2
    hits = 0
    for row in g[1:]:
        cand = o[1] if single else keyed.get(row[0].strip().lower())
        if not cand:
            continue
        gnums = [_num(v) for v in (row if single else row[1:])]
        onums = [_num(v) for v in (cand if single else cand[1:])]
        pairs = [(a, b) for a, b in zip(gnums, onums, strict=False) if a is not None and b is not None]
        if pairs and all(abs(a - b) <= max(tol, 1e-9) + 1e-9 for a, b in pairs):
            hits += 1
    return hits / (len(g) - 1)


def score_text(ours: str, gold: str, sources: str, gold_sources: str) -> float:
    words = lambda t: set(re.findall(r"[a-z0-9]+", t.lower())) - {"the", "a", "of", "and", "to", "in", "is"}  # noqa: E731
    gw = words(gold)
    overlap = len(gw & words(ours)) / max(len(gw), 1)
    gdocs = re.findall(r"[A-Z]{2,}-[A-Z0-9-]+|transcript \d+|qa_checklist", gold_sources or "")
    cited = any(d.split()[0] in sources for d in gdocs) if gdocs else True
    return round(0.5 * overlap + 0.5 * cited, 3)


def _read_extra(path: str, seen: set[str]) -> list[dict]:
    """The 19:00 file, tolerantly: any delimiter and BOM, `question_id` and `question_text` under a few likely names,
    other columns optional, ids already answered skipped (so re-running is safe)."""
    raw = Path(path).read_text(encoding="utf-8-sig")
    dialect = csv.Sniffer().sniff(raw[:2000], delimiters=",;\t|") if raw.strip() else csv.excel
    out = []
    for r in csv.DictReader(io.StringIO(raw), dialect=dialect):
        r = {(k or "").strip().lower(): (v or "").strip() for k, v in r.items()}
        qid = r.get("question_id") or r.get("id") or r.get("qid")
        text = r.get("question_text") or r.get("question") or r.get("text")
        if qid and text and qid not in seen:
            out.append({**r, "question_id": qid, "question_text": text})
            seen.add(qid)
    print(f"{len(out)} extra questions read from {path}")
    return out


def main(extra: str | None = None) -> None:
    qs = list(csv.DictReader(open(REL / "data" / "benchmark_questions.csv")))
    if extra:
        qs += _read_extra(extra, {q["question_id"] for q in qs})
    gold = {r["question_id"]: r for r in csv.DictReader(open(REL / "labels" / "benchmark_dev_answers.csv"))}
    out_rows, report = [], []
    for q in qs:
        t0 = time.perf_counter()
        try:
            a = ask(q["question_text"], _as_of(q))
        except Exception as e:  # noqa: BLE001 - one bad question must not stop the submission; answer it as a refusal
            from nlq.pipeline import Answer

            a = Answer(q["question_text"], "refused", f"The system could not answer this question ({type(e).__name__}).",
                       "", refused=True)
        ms = round((time.perf_counter() - t0) * 1000)
        out_rows.append({"question_id": q["question_id"], "answer": a.answer, "sql_or_sources": a.sql_or_sources,
                         "refused": "true" if a.refused else "false"})
        rec = {"question_id": q["question_id"], "split": q.get("split"), "kind": a.kind, "refused": a.refused,
               "latency_ms": ms}
        g = gold.get(q["question_id"])
        if g:
            should_refuse = g["gold_answer"].lower().startswith("refuse")
            if should_refuse or a.refused:
                rec["score"] = 1.0 if (should_refuse and a.refused) else 0.0
            elif g["gold_sql_reference"]:
                rec["score"] = round(score_numeric(a.answer, g["gold_answer"], _tol(q.get("tolerance", ""))), 3)
            else:
                rec["score"] = score_text(a.answer, g["gold_answer"], a.sql_or_sources, g["gold_sources"])
            rec["gold"] = g["gold_answer"][:300]
            rec["ours"] = a.answer[:300]
        report.append(rec)
        print(f"{q['question_id']} {a.kind:12s} {ms:5d} ms  score={rec.get('score', '-')}")
    out = get_settings().deliverables_dir / "benchmark_answers.csv"
    out.parent.mkdir(exist_ok=True)
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["question_id", "answer", "sql_or_sources", "refused"])
        w.writeheader()
        w.writerows(out_rows)
    dev = [r["score"] for r in report if "score" in r]
    summary = {"questions": len(report), "dev_scored": len(dev), "dev_mean_score": round(sum(dev) / max(len(dev), 1), 3),
               "refused": sum(r["refused"] for r in report), "items": report}
    rp = get_settings().reports_dir / "benchmark.json"
    rp.parent.mkdir(parents=True, exist_ok=True)
    rp.write_text(json.dumps(summary, indent=2, default=str))
    print(f"\n{len(report)} answers -> {out}; dev mean score {summary['dev_mean_score']} on {len(dev)} dev questions")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", help="extra questions CSV (e.g. the 19:00 release)")
    main(ap.parse_args().questions)
