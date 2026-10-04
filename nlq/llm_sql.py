"""Language-model SQL for Ask: questions no certified metric covers, answered by a query the model writes.

Runs only after the refusal rules, the scope check and the certified compiler have had their turn, and only when a
language model is in use (mode not "rules", provider not offline) and the role may receive metrics. Safety stays in
code, never in the model:
  1. the model sees only the curated schema pack (nlq/schema_pack.py): no protected or personal column is in it;
  2. its SQL must pass the same guard as every Ask query (one read-only SELECT, allowed tables, no file functions,
     LIMIT <= 1000, no personal columns, no SELECT *) plus a column allowlist (only pack columns) and an aggregate
     rule (no customer, case, promise or account identifiers in the output);
  3. it runs read-only with a 20 s timeout and small-group suppression;
  4. a validation or execution error is sent back to the model at most twice, then Ask gives up with a refusal;
  5. the written insight sees only the returned rows (at most 50) and is dropped unless every number in it appears in
     those rows.
With LLM_PROVIDER=offline (or the rules mode) none of this runs and the model is never called.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import sqlglot
from sqlglot import exp

from common import ask_scope
from common.config import get_settings
from common.llm_mode import effective_provider
from llm.providers.offline import register

log = logging.getLogger(__name__)

CAVEAT = ("Not a certified metric: the model wrote this query from your question. "
          "Check the SQL before relying on it.")
GIVE_UP = "Refused: I could not turn that into a safe query. Try a certified metric, or rephrase the question."
MAX_ATTEMPTS = 3          # the first try plus two retries with the error text
ROW_CAP = 1000
TIMEOUT_S = 20.0
INSIGHT_ROWS = 50
# Output columns that would list individual customers, accounts, cases, promises or contacts.
IDENTIFIERS = {"case_id", "ptp_id", "contact_id", "account_id", "primary_account_id", "card_account_id", "loan_id",
               "deposit_account_id", "offer_id", "crm_customer_id", "coll_customer_ref", "src_customer_ref", "score_id",
               "entity_id", "golden_id", "current_ptp_id", "assignment_id"}


@register("nl_to_sql")
def nl_to_sql_offline(inputs: dict) -> dict:
    """Offline there is no model to write SQL: a clear 'cannot', so Ask keeps to certified metrics."""
    return {"sql": "", "tables": [], "confidence": 0.0,
            "explanation": "cannot: no language model is configured, so Ask answers certified metrics only."}


class Rejected(Exception):
    """The model's SQL was not accepted. `retry` False means the question itself is not allowed (personal or protected
    data), so the model is not asked again."""

    def __init__(self, message: str, retry: bool = True):
        super().__init__(message)
        self.retry = retry


@dataclass
class Result:
    status: str                       # answered | declined | refused | gave_up | unavailable
    sql: str = ""
    columns: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)
    tables: list[str] = field(default_factory=list)
    explanation: str = ""
    confidence: float | None = None
    reason: str = ""
    attempts: list[dict] = field(default_factory=list)
    suppressed: bool = False
    seconds: float = 0.0
    calls: int = 0


def enabled() -> bool:
    """Is the SQL path allowed for this request? Never for roles that may not receive metrics (agents), never in
    rules mode, never without a configured language model."""
    scope = ask_scope.current()
    if scope is not None and not scope.allow_metrics:
        return False
    return effective_provider() != "offline"


def _clean(sql: str) -> str:
    s = (sql or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```\w*", "", s).rstrip("`").strip()
    return s.rstrip().rstrip(";").strip()


def _top_selects(node: exp.Expression) -> list[exp.Select]:
    if isinstance(node, exp.Select):
        return [node]
    if isinstance(node, exp.Union):
        return _top_selects(node.left) + _top_selects(node.right)
    if isinstance(node, exp.Subquery):
        return _top_selects(node.this)
    return []


def tables_in(sql: str) -> list[str]:
    tree = sqlglot.parse_one(sql, read="duckdb")
    ctes = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
    return sorted({t.name.lower() for t in tree.find_all(exp.Table) if t.name and t.name.lower() not in ctes})


def check_sql(sql: str, pack, role: str | None = None, user_id: str | None = None) -> str:
    """The guarded SQL to run, or Rejected. Reuses nlq.guard.validate and nlq.executor.check_columns, then adds the
    pack's column allowlist and the aggregate rule."""
    from nlq.executor import check_columns
    from nlq.guard import GuardError, agent_row_filters, apply_row_filters, validate
    from nlq.schema_pack import blocked_columns

    sql = _clean(sql)
    if not sql:
        raise Rejected("Empty SQL")
    try:
        safe = validate(sql, set(pack.tables), max_limit=ROW_CAP)
    except GuardError as e:
        raise Rejected(str(e), retry="Protected" not in str(e)) from e
    try:
        check_columns(safe)
    except PermissionError as e:
        raise Rejected(str(e), retry="SELECT *" in str(e)) from e

    tree = sqlglot.parse_one(safe, read="duckdb")
    blocked = blocked_columns()
    aliases = {a.alias.lower() for a in tree.find_all(exp.Alias) if a.alias}
    aliases |= {c.name.lower() for ta in tree.find_all(exp.TableAlias) for c in ta.columns}
    for name in aliases:
        if name in blocked:
            raise Rejected(f"Personal or protected data can't be queried: {name}", retry=False)
        if name in pack.hidden:
            raise Rejected(f"Rename the output column '{name}': that name belongs to a column that is not available")
    visible = {c.lower() for c in pack.visible}
    for col in tree.find_all(exp.Column):
        n = col.name.lower()
        if not n:
            continue
        if n in blocked:
            raise Rejected(f"Personal or protected data can't be queried: {n}", retry=False)
        if n in pack.hidden:
            raise Rejected(f"Column '{n}' is not available to Ask. Use only the columns listed in SCHEMA.")
        if n not in visible and n not in aliases:
            raise Rejected(f"Column '{n}' does not exist in SCHEMA. Use only the columns listed there.")

    from nlq.schema_pack import TABLES

    used = tables_in(safe)
    if any(not TABLES[t].reference for t in used if t in TABLES):
        if not (tree.find(exp.AggFunc) or tree.find(exp.Group)):
            raise Rejected("Ask returns aggregates only: group and count, sum or average instead of listing rows.")
        for sel in _top_selects(tree):
            outs = [e.unalias() for e in sel.expressions]
            group = sel.args.get("group")
            keys = list(group.expressions) if group else []
            for e in outs + keys:
                if isinstance(e, exp.Column) and e.name.lower() in IDENTIFIERS:
                    raise Rejected(f"Ask returns aggregates only: do not output or group by {e.name.lower()}.")
    if role == "agent" and user_id:  # agents never reach this path; kept as a second lock
        safe, _ = apply_row_filters(safe, agent_row_filters(user_id))
    return safe


def _count_outputs(sql: str) -> set[str]:
    tree = sqlglot.parse_one(sql, read="duckdb")
    return {e.alias_or_name for sel in _top_selects(tree) for e in sel.expressions
            if isinstance(e.unalias(), exp.Count)}


def suppress_small_counts(sql: str, columns: list[str], rows: list[tuple]) -> tuple[list[tuple], bool]:
    """Counts under the small-group threshold are shown as '<10' (on top of the executor's own suppression)."""
    k = get_settings().suppression_min_group
    idx = [i for i, c in enumerate(columns) if c in _count_outputs(sql)]
    out, hit = [], False
    for r in rows:
        r2 = tuple("<10" if (i in idx and isinstance(v, int) and not isinstance(v, bool) and 0 < v < k) else v
                   for i, v in enumerate(r))
        hit = hit or r2 != tuple(r)
        out.append(r2)
    return out, hit


def run(safe: str) -> tuple[str, list[str], list[tuple]]:
    import duckdb

    from nlq.executor import execute

    try:
        return execute(safe, max_rows=ROW_CAP, timeout_s=TIMEOUT_S)
    except duckdb.InterruptException as e:
        raise Rejected(f"The query ran longer than {TIMEOUT_S:.0f} s. Write a simpler query.") from e
    except duckdb.Error as e:
        raise Rejected(f"DuckDB error: {str(e).splitlines()[0][:300]}") from e


def generate(question: str, as_of: date, schema_text: str, attempts: list[dict]) -> dict:
    from llm.client import complete_json

    return complete_json("nl_to_sql", 1, {"question": question, "as_of_date": str(as_of), "schema": schema_text,
                                          "previous_attempts": attempts}, "nl_to_sql")


def generate_and_run(question: str, as_of: date | None = None) -> Result:
    """Ask the model for SQL, check it, run it; retry with the error up to twice. Never raises for model problems."""
    from nlq.schema_pack import build

    t0 = time.perf_counter()
    as_of = as_of or get_settings().as_of_date
    scope = ask_scope.current()
    if not enabled():
        return Result("unavailable", reason="no language model in use, or the role may not receive metrics")
    role, user = (scope.role, scope.user_id) if scope else (None, None)
    pack = build(as_of, role)
    if not pack.tables:
        return Result("unavailable", reason="no tables for this role")
    schema_text = pack.text()
    res = Result("gave_up")
    for _ in range(MAX_ATTEMPTS):
        res.calls += 1
        try:
            out = generate(question, as_of, schema_text, res.attempts)
        except Exception as e:  # noqa: BLE001 - a bad reply counts as a failed attempt; Ask must not break
            res.attempts.append({"sql": "", "error": f"The reply was not the JSON asked for ({type(e).__name__})."})
            continue
        if out.get("_meta", {}).get("provider") == "offline":
            return Result("unavailable", reason="the language model was not reachable", calls=res.calls,
                          seconds=time.perf_counter() - t0)
        sql = _clean(str(out.get("sql") or ""))
        res.explanation = str(out.get("explanation") or "")[:400]
        try:
            res.confidence = float(out.get("confidence"))
        except (TypeError, ValueError):
            res.confidence = None
        if not sql:
            res.status, res.reason = "declined", res.explanation or "The model could not answer this from the data."
            break
        try:
            safe = check_sql(sql, pack, role, user)
            executed, cols, rows = run(safe)
        except Rejected as e:
            res.attempts.append({"sql": sql, "error": str(e)})
            if not e.retry:
                res.status, res.reason = "refused", f"Refused: {e}"
                break
            continue
        rows, res.suppressed = suppress_small_counts(executed, cols, rows)
        res.status, res.sql, res.columns = "answered", executed, list(cols)
        res.rows, res.tables = [list(r) for r in rows], tables_in(executed)
        break
    if res.status == "gave_up":
        res.reason = GIVE_UP
    res.seconds = time.perf_counter() - t0
    log.info("llm_sql %s after %d call(s) in %.1f s", res.status, res.calls, res.seconds)
    return res


# Insight: numbers checked against the rows

NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?(?:\s*(?:%|percent\b|k\b|thousand\b|million\b|m\b|bn\b|billion\b))?", re.I)
SNAKE = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")
MULT = {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6, "bn": 1e9, "billion": 1e9}


def _jsonable(v: Any) -> Any:
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


def _numbers_in(text: str) -> list[tuple[float, float]]:
    """(value, tolerance) for every number written in `text`, tolerance from the precision it is written with."""
    out = []
    for m in NUMBER.finditer(text):
        raw = m.group(0)
        num = re.match(r"[\d,]*\d(?:\.\d+)?", raw).group(0).replace(",", "")
        unit = raw[len(re.match(r"[\d,.]+", raw).group(0)):].strip().lower()
        mult = MULT.get(unit, 1.0)
        decimals = len(num.split(".")[1]) if "." in num else 0
        out.append((float(num) * mult, 0.5 * 10 ** -decimals * mult + 1e-9))
    return out


def verify_insight(text: str, question: str, columns: list[str], rows: list[list[Any]]) -> bool:
    """True if every number in the insight appears in the rows (allowing for rounding to the precision it is written
    with, thousands separators and fractions shown as percentages) and every snake_case name is a result column or a
    value. Numbers the user typed in the question and the row count are also allowed."""
    allowed: list[float] = [float(len(rows))]
    words = {c.lower() for c in columns}
    for r in rows:
        for v in r:
            if isinstance(v, bool) or v is None:
                continue
            if isinstance(v, (int, float, Decimal)):
                f = abs(float(v))
                allowed += [f, f * 100] if f <= 1 else [f]
            else:
                s = str(_jsonable(v))
                words.add(s.lower())
                allowed += [x for x, _ in _numbers_in(s)]
    allowed += [x for x, _ in _numbers_in(question)]
    for x, tol in _numbers_in(text):
        if not any(abs(a - x) <= tol for a in allowed):
            return False
    return all(w in words for w in SNAKE.findall(text.lower()))


def template_insight(rows: list[list[Any]]) -> str:
    if not rows:
        return "No rows matched this question."
    return f"{len(rows)} row(s) returned by a query the language model wrote (not a certified metric)."


def write_insight(question: str, sql: str, columns: list[str], rows: list[list[Any]]) -> tuple[str, bool]:
    """(text, written_by_model). The model sees the question, the SQL and at most 50 result rows, nothing else."""
    if not rows:
        return template_insight(rows), False
    from llm.client import complete_json

    shown = [[_jsonable(v) for v in r] for r in rows[:INSIGHT_ROWS]]
    try:
        out = complete_json("ask_insight", 2, {"question": question, "sql": sql, "columns": columns, "rows": shown,
                                               "row_count": len(rows)}, "ask_insight")
    except Exception:  # noqa: BLE001 - no insight is better than a broken answer
        return template_insight(rows), False
    text = str(out.get("insight") or "").strip()
    if out.get("_meta", {}).get("provider") == "offline" or not text:
        return template_insight(rows), False
    if not verify_insight(text, question, columns, shown):
        log.info("insight dropped: a number or column is not in the rows: %s", text)
        return template_insight(rows), False
    return text, True


def citations(sql: str, tables: list[str]) -> list[dict]:
    """Sources in the policy answers' shape ({doc_id, section, quote}) plus kind, ref, label and tables."""
    from nlq.schema_pack import TABLES

    label = f"Query on {', '.join(tables)}" if tables else "Query"
    out = [{"kind": "sql", "doc_id": "sql", "section": "generated query", "quote": sql, "ref": sql, "label": label,
            "tables": tables}]
    for t in tables:
        desc = TABLES[t].description if t in TABLES else t
        out.append({"kind": "table", "doc_id": t, "section": f"silver.{t}", "quote": desc, "ref": t, "label": desc,
                    "tables": [t]})
    return out


def answer(question: str, as_of: date | None = None):
    """An Ask Answer from model-written SQL, a refusal Answer, or None (no model, or the model declined)."""
    from nlq.pipeline import Answer, _csv

    res = generate_and_run(question, as_of)
    if res.status in ("unavailable", "declined"):
        return None
    if res.status in ("refused", "gave_up"):
        return Answer(question, "refused", res.reason, "", refused=True, refusal_reason=res.reason,
                      answered_by="language model")
    insight, by_model = write_insight(question, res.sql, res.columns, res.rows)
    caveats = [CAVEAT]
    if res.explanation:
        caveats.append(f"How the model read the question: {res.explanation}")
    if res.suppressed:
        caveats.append("Counts under 10 are hidden (shown as <10).")
    if not by_model and res.rows:
        caveats.append("The written insight is a template: the model's wording was not used.")
    text = _csv(res.columns, [tuple(r) for r in res.rows]) if res.rows else "No rows matched this question."
    return Answer(question, "metric", text, res.sql, columns=res.columns, rows=res.rows, caveats=caveats,
                  chips={"metric": None, "dimensions": [], "filters": [], "time": None, "certified": False,
                         "generated": True, "tables": res.tables, "confidence": res.confidence,
                         "attempts": res.calls},
                  citations=citations(res.sql, res.tables), answered_by="language model", generated=True,
                  insight=insight)
