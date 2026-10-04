"""Collections Ask: one entry point for every plain-English question (Layer 2).

Order: refusal rules -> case call summary -> policy/document questions -> certified-metric SQL -> language-model
SQL (only with a model in use, never certified) -> refuse.
Every answer carries its working: the SQL it ran (metric questions) or the documents and sections it used,
plus caveats (default filters, incidents in the period, causal warnings). The offline path needs no LLM.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import UTC, date
from typing import Any

from common import ask_scope
from common.config import get_settings

POLICY_INTENT = re.compile(
    r"^(can|may|should|must|is|are|does|do)\b|\b(what (must|should)|allowed|permitted|maximum|minimum|limit|policy|procedure|rule|grace "
    r"period|process|steps|what happens|how should|how do we|what do we do|how long does|programme|program last|what should the agent|why did|what happened)\b", re.I)
QUANT = re.compile(r"\b(worked best|most effective|what share|share of|percentage|how many|how much|what (is|was) the (\w+ ){0,3}(rate|average|cost|number|count)|"
                   r"average|rate\b|per case|by (queue|site|province|product|bucket|channel|hour|month|team))", re.I)
CASE_SUMMARY = re.compile(r"\b(CS-\d{4}-\d+)\b")
# A question that asks for a number over a period or a breakdown (not a rule). If no certified metric fits it, the
# nearest policy paragraph would be a wrong answer, so Ask refuses and says which measure is missing.
DATA_SHAPE = re.compile(
    r"\bby (queue|site|province|product|bucket|channel|hour|month|team|agent|day|week|region|language|segment|type|"
    r"reason|outcome)\b|\b(in|during|for|since|between) (january|february|march|april|may|june|july|august|september|"
    r"october|november|december)\b|\b(last|past|this) (\d+ )?(day|week|month|quarter|year)s?\b|\btoday\b|"
    r"\baverage\b|\bper (case|call|contact|agent|day)\b|\btotal (number|amount|count)\b", re.I)
POLICY_WORDING = re.compile(
    r"\b(can|may|must|should|allowed|permitted|required|need to|maximum|minimum|policy|procedure|rule|grace|consent|"
    r"programme|program last|what happens|what should)\b", re.I)


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
    freshness: str | None = None      # when the warehouse behind the answer was built (ISO, UTC)
    answered_by: str = "rules"        # rules | language model (set when a model matched the metric or worded the answer)
    generated: bool = False           # True when a language model wrote the SQL (nlq/llm_sql.py): not a certified metric
    insight: str | None = None        # written insight for generated SQL answers (numbers checked against the rows)


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


def _metric(question: str, as_of: date, force_metric: str | None = None, chips: dict | None = None) -> Answer | None:
    from nlq.executor import execute
    from semantic.compiler import compile_question

    c = compile_question(question, as_of, force_metric, chips)
    if c is None:
        return None
    scope = ask_scope.current()
    if scope is not None and not scope.allow_metrics:
        raise PermissionError(ask_scope.METRICS_DENIED)  # decided before any SQL runs
    sql, cols, rows = execute(c.sql)
    caveats = list(c.caveats)
    if re.search(r"\b(which|what) customers\b", question, re.I):
        caveats.append("Ask does not list customers (aggregates only), so this is the count of matching records.")
    if c.time_range:
        start = c.time_range.previous.start if c.time_range.previous else c.time_range.start
        caveats += _incident_caveats(start, c.time_range.end)
    if c.metric_id.endswith("_count") and len(rows) == 1 and all(v in (0, None) for v in rows[0]):
        rows = []  # a count of nothing is "no rows", not a row that says 0: the written answer then cites no number
    text = _csv(cols, rows) if rows else "No rows matched this question."
    verdict = _comparison_verdict(question, cols, rows)
    if verdict:
        text = verdict + "\n" + text
    return Answer(question, "metric", text, sql, columns=cols, rows=[list(r) for r in rows],
                  caveats=caveats, chips={"metric": c.metric_id, "dimensions": c.dimensions, "filters": c.filters,
                                          "time": c.time_label})


def _metric_or_generated(question: str, as_of: date) -> Answer | None:
    """The certified metric, unless it could not split by what was asked ("Not split by product"). With a language
    model in use, that question goes to the guarded model-written SQL instead of a half answer."""
    a = _metric(question, as_of)
    if a is not None and any(c.startswith("Not split by") for c in a.caveats):
        g = _llm_sql(question, as_of)
        if g is not None and not g.refused:
            return g
    return a


def _metric_via_llm(question: str, as_of: date) -> Answer | None:
    """Rules didn't recognise the question: the configured LLM picks which certified metric it asks for (closed list,
    checked against the question's own words); breakdowns, filters and period still come from the rules, and the SQL
    goes through the same compiler and guard as any typed question."""
    from nlq.rewrite import choose_metric

    scope = ask_scope.current()
    if scope is not None and not scope.allow_metrics:
        return None  # not allowed to receive a metric by any method, so the model is not even asked
    if POLICY_WORDING.search(question) or POLICY_INTENT.search(question):
        return None  # a rule or policy question: the documents answer it, not a metric
    try:
        pick = choose_metric(question, as_of)
    except Exception:  # noqa: BLE001 - an LLM problem must never break Ask; the rules' answer (a refusal) stands
        return None
    if not pick:
        return None
    a = _metric(question, as_of, force_metric=pick["metric_id"])
    if a is None:
        return None
    if any(c.startswith("Not split by") for c in a.caveats):
        g = _llm_sql(question, as_of)  # the metric cannot split as asked: guarded model-written SQL, not a half answer
        if g is not None and not g.refused:
            return g
    a.chips["interpreted_as"] = pick["metric_id"]
    a.answered_by = "language model"
    a.caveats.insert(0, f"A language model matched this question to the certified metric {pick['metric_id']} "
                        f"(\"{pick['measure']}\"); the SQL below is generated by rules, not by the model.")
    return a


def _llm_sql(question: str, as_of: date, late: bool = False) -> Answer | None:
    """No certified metric fits: a language model writes the SQL (nlq/llm_sql.py), guarded and labelled as generated.
    A question worded like a rule goes to the policy documents first (late=True runs it only after they fail)."""
    if bool(POLICY_WORDING.search(question)) != late:
        return None
    if late and not (QUANT.search(question) or DATA_SHAPE.search(question)):
        return None  # a policy-worded question the documents could not answer is not a data question: no model-written SQL
    from nlq import llm_sql

    if not llm_sql.enabled():
        return None  # rules mode, no model configured, or a role that may not receive metrics: the model is not called
    return llm_sql.answer(question, as_of)


MY_CASES = re.compile(r"\b(show|list|which|what are|give me)\b.{0,25}\bmy\b.{0,30}\b(cases?|customers?|accounts?)\b", re.I)


def _my_cases(question: str) -> Answer | None:
    """An agent asking for their own cases ("show my open cases with a broken promise"): rows of THEIR cases only, chosen by
    the signed-in agent id and never by the question. Not a portfolio metric, so agents may ask it."""
    scope = ask_scope.current()
    if scope is None or scope.role != "agent" or not scope.user_id or not MY_CASES.search(question):
        return None
    from nlq.executor import execute

    who = scope.user_id.replace("'", "''")
    where = [f"c.assigned_agent_id = '{who}'"]
    notes = ["Only your own cases are listed."]
    if re.search(r"\bclosed\b", question, re.I):
        where.append("c.outcome IS NOT NULL")
    else:
        where.append("c.outcome IS NULL")
        notes.append("Open cases only.")
    if re.search(r"broken promise|broke a promise|broken ptp", question, re.I):
        where.append("c.promises_broken > 0")
        notes.append("With at least one broken promise.")
    if re.search(r"hardship", question, re.I):
        where.append("c.hardship_flag")
        notes.append("With a hardship flag.")
    sql = ("SELECT c.case_id, c.primary_product, c.current_dpd, c.total_overdue, c.promises_broken FROM collections_cases c "
           f"WHERE {' AND '.join(where)} ORDER BY c.total_overdue DESC LIMIT 50")
    sql, cols, rows = execute(sql)
    text = _csv(cols, rows) if rows else "None of your cases match."
    return Answer(question, "cases", text, sql, columns=cols, rows=[list(r) for r in rows], caveats=notes,
                  chips={"metric": None, "dimensions": [], "filters": notes, "time": None})


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
    from rag.answer import answer_with_llm

    a = answer_with_llm(question)
    if a["refused"]:
        return None
    seen: set[tuple] = set()
    a["citations"] = [c for c in a["citations"] if (k := (c["doc_id"], c["section"])) not in seen and not seen.add(k)]
    src = "; ".join(f"{c['doc_id']} {c['section']}" for c in a["citations"])
    ans = Answer(question, "policy", a["answer"], src, citations=a["citations"])
    if a.get("by_llm"):
        ans.answered_by = "language model"
        ans.caveats.append("Worded by a language model from the quoted policy sections; each quote is checked against the document.")
    return ans


def _call_summary(question: str) -> Answer | None:
    m = CASE_SUMMARY.search(question)
    if not m or not re.search(r"summar|call|said|agree|transcript", question, re.I):
        return None
    from decisioning.post_call import summarise

    scope = ask_scope.current()
    if scope is not None and scope.case_allowed is not None and not scope.case_allowed(m.group(1)):
        raise PermissionError(scope.case_denied_reason)
    s = summarise(case_id=m.group(1))
    if s is None:
        return Answer(question, "call_summary", f"No recorded call found for case {m.group(1)}.", "")
    return Answer(question, "call_summary", s["summary"], f"transcript {s['transcript_id']}",
                  chips={"case_id": s["case_id"], "call": s["call_start_ts"]})


INTERACTION_INTENT = re.compile(
    r"\b(notes?|transcripts?|recordings?|voicemails?|voice|conversations?)\b|\bwhat (did|has|have) .{0,40}\b(say|said|tell|told|"
    r"mention\w*|promise\w*|ask\w*|request\w*)\b|\b(said|told|mentioned) (that|they|he|she)\b", re.I)
INTERACTION_AGGREGATE = re.compile(r"\b(how many|number of|count|average|total|rate|percentage|share|per)\b", re.I)


def _interactions(question: str) -> Answer | None:
    """Questions about what was said or written on a case: agent notes, call transcripts and voice speech-to-text,
    read only through the access filter, quoted and cited (rag/interactions.py). Never answers without a citation."""
    if not INTERACTION_INTENT.search(question) or INTERACTION_AGGREGATE.search(question):
        return None
    from rag import interactions

    scope = ask_scope.current()
    m = CASE_SUMMARY.search(question)
    out = interactions.answer(question, scope, case_id=m.group(1) if m else None, k=8)
    if m and out["refused"] and not str(out.get("refusal_reason") or "").startswith("Refused"):
        # "what do the notes say about case X": the case id and the word "case" are not search terms, so ask for its recent record
        out = interactions.answer("Summarise the recent notes and calls on this case", scope, case_id=m.group(1), k=8)
    if out["refused"]:
        reason = out.get("refusal_reason") or ""
        if reason.startswith("Refused"):
            raise PermissionError(reason)
        return None
    cites = out["citations"]
    ans = Answer(question, "interactions", out["answer"], "; ".join(c["label"] for c in cites), citations=cites)
    if out.get("by_llm"):
        ans.answered_by = "language model"
        ans.caveats.append("Worded by a language model from the quoted notes and calls; each quote is checked against the record.")
    return ans


def _warehouse_built_at() -> str | None:
    from datetime import datetime

    p = get_settings().warehouse_path
    return datetime.fromtimestamp(p.stat().st_mtime, tz=UTC).isoformat(timespec="seconds") if p.exists() else None


def ask(question: str, as_of: date | None = None, chips: dict | None = None) -> Answer:
    """`chips` (metric, dimensions, filters, time) are the analyst's corrections to what Ask understood: the answer
    is compiled from them by the same certified compiler, under the same scope and refusal rules."""
    a = _ask_from_chips(question, as_of, chips) if chips is not None else _ask(question, as_of)
    if not a.refused and a.kind == "metric":
        a.freshness = _warehouse_built_at()
    return a


def _ask_from_chips(question: str, as_of: date | None, chips: dict) -> Answer:
    from nlq.refusal import check
    from semantic.compiler import ChipError

    as_of = as_of or get_settings().as_of_date
    reason = check(question)
    try:
        if not reason:
            a = _metric(question, as_of, chips=chips)
            if a is not None:
                return a
            reason = "Outside scope: the edited chips do not map to a certified metric."
    except (PermissionError, ChipError) as e:
        reason = str(e)
    return Answer(question, "refused", reason, "", refused=True, refusal_reason=reason)


def _ask(question: str, as_of: date | None = None) -> Answer:
    from nlq.refusal import check

    as_of = as_of or get_settings().as_of_date
    reason = check(question)
    if reason:
        return Answer(question, "refused", reason, "", refused=True, refusal_reason=reason)
    policy_first = bool(POLICY_INTENT.search(question)) and not QUANT.search(question)
    for step in ([_my_cases, _call_summary, _interactions, _policy, lambda q: _metric(q, as_of), lambda q: _metric_via_llm(q, as_of)]
                 if policy_first
                 else [_my_cases, _call_summary, _interactions, lambda q: _metric_or_generated(q, as_of),
                       lambda q: _metric_via_llm(q, as_of), lambda q: _llm_sql(q, as_of), _policy, lambda q: _llm_sql(q, as_of, late=True)]):
        if step is _policy and not policy_first and DATA_SHAPE.search(question) and not POLICY_WORDING.search(question):
            reason = ("Outside scope: no certified metric covers this measure. Ask answers only the certified "
                      "collections metrics (cure, roll, promise, contact, cost, hardship, delinquency, write-off, DPD).")
            return Answer(question, "refused", reason, "", refused=True, refusal_reason=reason)
        try:
            a = step(question)
        except PermissionError as e:
            return Answer(question, "refused", str(e), "", refused=True, refusal_reason=str(e))
        if a is not None:
            return a
    reason = "Outside scope: this question doesn't map to a certified metric or a current policy document."
    return Answer(question, "refused", reason, "", refused=True, refusal_reason=reason)
