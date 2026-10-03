"""Collections Ask: one entry point for every plain-English question (Layer 2).

Order: refusal rules -> case call summary -> policy/document questions -> certified-metric SQL -> refuse.
Every answer carries its working: the SQL it ran (metric questions) or the documents and sections it used,
plus caveats (default filters, incidents in the period, causal warnings). The offline path needs no LLM.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from common.config import get_settings

POLICY_INTENT = re.compile(
    r"^(can|may|should|must|is|are|does|do)\b|\b(what (must|should)|allowed|permitted|policy|procedure|rule|grace "
    r"period|how long does|programme|program last|what should the agent|why did|what happened)\b", re.I)
QUANT = re.compile(r"\b(worked best|most effective|what share|share of|percentage|how many|how much|what (is|was) the (\w+ ){0,3}(rate|average|cost|number|count)|"
                   r"average|rate\b|per case|by (queue|site|province|product|bucket|channel|hour|month|team))", re.I)
CASE_SUMMARY = re.compile(r"\b(CS-\d{4}-\d+)\b")


@dataclass
class Answer:
    question: str
    kind: str                         # metric | policy | call_summary | refused
    answer: str
    sql_or_sources: str = ""
    refused: bool = False
    refusal_reason: str | None = None
    columns: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)
    chips: dict[str, Any] = field(default_factory=dict)
    citations: list[dict] = field(default_factory=list)


def _csv(cols: list[str], rows: list[tuple]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(cols)
    for r in rows:
        w.writerow(["" if v is None else (round(v, 4) if isinstance(v, float) else v) for v in r])
    return buf.getvalue().strip()


def _incident_caveats(start: date | None, end: date | None) -> list[str]:
    if not start:
        return []
    from common.db import warehouse
    con = warehouse(read_only=True)
    try:
        rows = con.execute("""SELECT event_id, description FROM silver.ops_events
                              WHERE CAST(start_ts AS DATE) <= ? AND CAST(end_ts AS DATE) >= ?
                                AND event_type NOT IN ('policy_change')""", [end or start, start]).fetchall()
    finally:
        con.close()
    return [f"Incident in this period: {eid}: {desc}." for eid, desc in rows]


def _metric(question: str, as_of: date) -> Answer | None:
    from nlq.executor import execute
    from semantic.compiler import compile_question

    c = compile_question(question, as_of)
    if c is None:
        return None
    sql, cols, rows = execute(c.sql)
    caveats = list(c.caveats)
    if c.time_range:
        start = c.time_range.previous.start if c.time_range.previous else c.time_range.start
        caveats += _incident_caveats(start, c.time_range.end)
    text = _csv(cols, rows)
    verdict = _comparison_verdict(question, cols, rows)
    if verdict:
        text = verdict + "\n" + text
    return Answer(question, "metric", text, sql, columns=cols, rows=[list(r) for r in rows],
                  caveats=caveats, chips={"metric": c.metric_id, "dimensions": c.dimensions, "filters": c.filters,
                                          "time": c.time_label})


def _comparison_verdict(question: str, cols: list[str], rows: list[tuple]) -> str | None:
    """For yes/no comparison questions over a two-group result ('do certified agents achieve a higher cure
    rate?'), state the direction from the data, falling back to the next rate column when the first is tied."""
    if not re.match(r"^\s*(in the [^,]+,\s*)?(do|does|did|is|are)\b", question, re.I) or len(rows) != 2:
        return None
    rate_idx = [i for i, c in enumerate(cols) if c.endswith("_pct") or c.startswith("avg")]
    for i in rate_idx:
        (g1, v1), (g2, v2) = (rows[0][0], rows[0][i]), (rows[1][0], rows[1][i])
        if v1 is None or v2 is None or v1 == v2:
            continue
        hi, lo = ((g1, v1), (g2, v2)) if v1 > v2 else ((g2, v2), (g1, v1))
        group_true = next((g for g in (g1, g2) if g in (True, "true", "True")), None)
        yes = (group_true is None) or hi[0] == group_true
        note = "" if i == rate_idx[0] else f" ({cols[rate_idx[0]]} is equal for both groups, so compared on {cols[i]})"
        return (f"{'Yes' if yes else 'No'}: {cols[0]}={hi[0]} has the higher {cols[i]} ({hi[1]} vs {lo[1]}){note}. "
                "Observed difference; the randomised pilot makes it causal, but check the group sizes.")
    return None


def _policy(question: str) -> Answer | None:
    from rag.answer import answer_question

    a = answer_question(question)
    if a["refused"]:
        return None
    src = "; ".join(f"{c['doc_id']} {c['section']}" for c in a["citations"])
    return Answer(question, "policy", a["answer"], src, citations=a["citations"])


def _call_summary(question: str) -> Answer | None:
    m = CASE_SUMMARY.search(question)
    if not m or not re.search(r"summar|call|said|agree|transcript", question, re.I):
        return None
    from decisioning.post_call import summarise

    s = summarise(case_id=m.group(1))
    if s is None:
        return Answer(question, "call_summary", f"No recorded call found for case {m.group(1)}.", "")
    return Answer(question, "call_summary", s["summary"], f"transcript {s['transcript_id']}",
                  chips={"case_id": s["case_id"], "call": s["call_start_ts"]})


def ask(question: str, as_of: date | None = None) -> Answer:
    from nlq.refusal import check

    as_of = as_of or get_settings().as_of_date
    reason = check(question)
    if reason:
        return Answer(question, "refused", reason, "", refused=True, refusal_reason=reason)
    policy_first = bool(POLICY_INTENT.search(question)) and not QUANT.search(question)
    for step in ([_call_summary, _policy, lambda q: _metric(q, as_of)] if policy_first
                 else [_call_summary, lambda q: _metric(q, as_of), _policy]):
        try:
            a = step(question)
        except PermissionError as e:
            return Answer(question, "refused", str(e), "", refused=True, refusal_reason=str(e))
        if a is not None:
            return a
    reason = "Outside scope: this question doesn't map to a certified metric or a current policy document."
    return Answer(question, "refused", reason, "", refused=True, refusal_reason=reason)
