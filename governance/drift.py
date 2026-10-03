"""S3 schema-drift telemetry with a drafted fix that an engineer approves.

Per load: row count, null rate per column, new or missing columns, type changes. The known case in the release is
`contact_history.channel` replaced by `channel_v2` on 26 Sep (ops_events REL-0926, reference_documents release note).

* Detection is plain arithmetic on two snapshots of a table (`detect`). It matches a change to `ops_events`
  (platform_release, data_feed_issue) and to release notes, so people see the likely reason.
* The fix is a drafted mapping for the silver model (`draft_fix`). The diff is always built by rules here. The language
  model (prompt `drift_fix`) may only improve the wording of the explanation, and the offline handler below writes it
  deterministically, so `LLM_PROVIDER=offline` always works.
* A fix starts as `pending_engineer_approval` and is never applied by the app. Only the data steward role (the
  Collections Data Engineering lead) may approve it, and the approval is audited. Approving records the decision; an
  engineer makes the change in the dbt project.

Drift fixes live in the ops store (`drift_fixes`, created on first use).
"""

from __future__ import annotations

import datetime as dt
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from common.config import ROOT
from common.db import ops
from common.hashing import stable_hash
from governance import audit
from llm.providers.offline import register

APPROVERS = {"data_steward", "steward"}
PENDING = "pending_engineer_approval"
NULL_JUMP_MIN = 0.05  # a null-rate change smaller than this is not reported
REPLACED_NULL_JUMP = 0.4  # a column that goes this much emptier can be the old half of a rename
MODEL_DIR = Path("pipeline/models/silver")
TIME_COLUMNS = {"contact_history": "contact_ts_utc"}  # tables we can slice by time in the warehouse

SCHEMA = """
CREATE TABLE IF NOT EXISTS drift_fixes (
    fix_id       TEXT PRIMARY KEY,
    table_name   TEXT NOT NULL,
    change_json  TEXT NOT NULL,
    description  TEXT NOT NULL,
    diff         TEXT NOT NULL,
    explanation  TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending_engineer_approval',
    applied      INTEGER NOT NULL DEFAULT 0,
    drafted_by   TEXT NOT NULL,
    created_ts   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    decided_by   TEXT,
    decided_ts   TEXT,
    decision_note TEXT
);
"""


# ------------------------------------------------------------------ profiling and detection
def _type_of(values: Iterable[Any]) -> str | None:
    kinds = set()
    for v in values:
        if v is None or v == "":
            continue
        if isinstance(v, bool):
            kinds.add("boolean")
        elif isinstance(v, int):
            kinds.add("integer")
        elif isinstance(v, float):
            kinds.add("number")
        elif isinstance(v, dt.datetime):
            kinds.add("timestamp")
        elif isinstance(v, dt.date):
            kinds.add("date")
        elif isinstance(v, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
            kinds.add("date")
        else:
            kinds.add("text")
    if not kinds:
        return None
    return "number" if kinds == {"integer", "number"} else (sorted(kinds)[0] if len(kinds) == 1 else "mixed")


def profile(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Row count, and per column the null rate and type. A column is present when any row carries the key."""
    cols = list(dict.fromkeys(c for r in rows for c in r))
    n = len(rows)
    return {"row_count": n, "columns": {
        c: {"null_rate": (sum(r.get(c) in (None, "") for r in rows) / n) if n else 0.0,
            "type": _type_of(r.get(c) for r in rows)} for c in cols}}


def profile_from_warehouse(con, table: str, start: dt.datetime, end: dt.datetime) -> dict[str, Any]:
    """The same profile for a time slice of a silver table. A column that is empty for the whole slice is absent."""
    ts = TIME_COLUMNS[table]
    cols = con.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_schema='silver' "
                       "AND table_name = ? ORDER BY ordinal_position", [table]).fetchall()
    exprs = ", ".join(f'count("{c}")' for c, _ in cols)
    row = con.execute(f"SELECT count(*), {exprs} FROM silver.{table} WHERE {ts} >= ? AND {ts} < ?",
                      [start, end]).fetchone()
    n = row[0]
    out = {}
    for (c, t), nn in zip(cols, row[1:], strict=True):
        if n and nn:
            out[c] = {"null_rate": 1 - nn / n, "type": t.lower()}
    return {"row_count": n, "columns": out}


def _similar(old: str, new: str) -> bool:
    return new.startswith(old) or old.startswith(new) or new.removeprefix("new_") == old


def detect(table: str, baseline: Sequence[Mapping[str, Any]] | Mapping[str, Any],
           new: Sequence[Mapping[str, Any]] | Mapping[str, Any], ops_events: Sequence[Any] = (),
           release_notes: Sequence[Any] = ()) -> dict[str, Any]:
    """Compare two snapshots (lists of rows, or ready profiles). Returns the drift and, when columns changed, the
    pairs that look like renames."""
    b = baseline if isinstance(baseline, Mapping) else profile(baseline)
    n = new if isinstance(new, Mapping) else profile(new)
    bc, nc = b["columns"], n["columns"]
    added, removed = sorted(set(nc) - set(bc)), sorted(set(bc) - set(nc))
    common = sorted(set(bc) & set(nc))
    nulls = {c: round(nc[c]["null_rate"] - bc[c]["null_rate"], 4) for c in common}
    nulls = {c: v for c, v in nulls.items() if abs(v) >= NULL_JUMP_MIN}
    types = [{"column": c, "from": bc[c]["type"], "to": nc[c]["type"]} for c in common
             if bc[c]["type"] and nc[c]["type"] and bc[c]["type"] != nc[c]["type"]]
    gone = removed + [c for c, v in nulls.items() if v >= REPLACED_NULL_JUMP and c not in removed]
    renames, used = [], set()
    for old in gone:
        for new_col in added:
            if new_col in used:
                continue
            same_type = bc[old]["type"] in (None, nc[new_col]["type"]) or nc[new_col]["type"] is None
            if _similar(old, new_col) and same_type:
                renames.append({"from": old, "to": new_col, "complete": old in removed})
                used.add(new_col)
                break
    if not renames and len(removed) == 1 and len(added) == 1 and bc[removed[0]]["type"] == nc[added[0]]["type"]:
        renames.append({"from": removed[0], "to": added[0], "complete": True})  # one out, one in, same type
    rc = (n["row_count"] - b["row_count"]) / b["row_count"] if b["row_count"] else None
    return {"table": table, "added_columns": added, "removed_columns": removed, "renames": renames,
            "type_changes": types, "row_count_baseline": b["row_count"], "row_count_new": n["row_count"],
            "row_count_change": None if rc is None else round(rc, 4), "null_rate_changes": nulls,
            "explanation_sources": explain(table, ops_events, release_notes),
            "changed": bool(added or removed or types)}


def explain(table: str, ops_events: Sequence[Any], release_notes: Sequence[Any]) -> list[str]:
    """ops_events (platform_release, data_feed_issue) on this table, and release notes about it."""
    def g(e: Any, k: str, d: Any = None) -> Any:
        return e.get(k, d) if isinstance(e, Mapping) else getattr(e, k, d)

    out = []
    for e in ops_events:
        tables = g(e, "affected_tables") or []
        tables = [x.strip(' "[]') for x in tables.split(",")] if isinstance(tables, str) else list(tables)
        if table in tables and g(e, "event_type") in ("platform_release", "data_feed_issue"):
            out.append(str(g(e, "event_id")))
    for d in release_notes:
        if str(g(d, "doc_type")) == "release_note" and table in str(g(d, "related_table", "")):
            out.append(str(g(d, "doc_id")))
    return list(dict.fromkeys(out))


# ------------------------------------------------------------------ the drafted fix
def model_path(table: str) -> Path:
    return MODEL_DIR / f"stg_{table}.sql"


def _model_text(table: str) -> str | None:
    p = ROOT / model_path(table)
    return p.read_text() if p.exists() else None


def build_diff(table: str, change: Mapping[str, Any], model_text: str | None = None) -> str:
    """The mapping as a diff for the silver model. Rules only."""
    path = model_path(table)
    lines = [f"--- {path}", f"+++ {path} (proposed, not applied)"]
    for r in change.get("renames", []):
        new_expr = f"coalesce(nullif({r['to']}, ''), nullif({r['from']}, '')) as {r['from']}"
        lines += [f"-    {r['from']},", f"+    {new_expr},"]
    paired = {r["to"] for r in change.get("renames", [])} | {r["from"] for r in change.get("renames", [])}
    for c in change.get("removed_columns", []):
        if c not in paired:
            lines.append(f"-    {c},  -- missing from the new load: confirm with the source owner")
    for c in change.get("added_columns", []):
        if c not in paired:
            lines.append(f"+    {c},  -- new column: add to the model if it is needed")
    for t in change.get("type_changes", []):
        cast = f"try_cast({t['column']} as {t['to']}) as {t['column']}"
        lines += [f"-    {t['column']},", f"+    {cast},  -- was {t['from']}"]
    if len(lines) == 2:
        lines.append("  (no column change: only row-count or null-rate movement, nothing to map)")
    return "\n".join(lines)


def describe(table: str, change: Mapping[str, Any]) -> str:
    bits = [f"map {r['from']} -> {r['to']}" for r in change.get("renames", [])]
    bits += [f"cast {t['column']} to {t['to']}" for t in change.get("type_changes", [])]
    paired = {r["to"] for r in change.get("renames", [])} | {r["from"] for r in change.get("renames", [])}
    bits += [f"check removed {c}" for c in change.get("removed_columns", []) if c not in paired]
    bits += [f"check new {c}" for c in change.get("added_columns", []) if c not in paired]
    return f"{table}: " + ", ".join(bits)


def offline_explanation(inputs: Mapping[str, Any]) -> str:
    table = inputs["table"]
    parts = []
    for r in inputs.get("renames", []):
        parts.append(f"Column {r['from']} in {table} appears to have been replaced by {r['to']}"
                     + ("" if r.get("complete") else " (the old column is still partly filled)") + ".")
    for t in inputs.get("type_changes", []):
        parts.append(f"Column {t['column']} changed type from {t['from']} to {t['to']}.")
    if inputs.get("explanation_sources"):
        parts.append("Likely reason: " + ", ".join(inputs["explanation_sources"]) + ".")
    if inputs.get("model_already_reads_new"):
        parts.append("The silver model already reads the new name, so the engineer may only need to confirm and close.")
    parts.append("This is a draft for an engineer to review. Nothing is applied automatically.")
    return " ".join(parts)


@register("drift_fix")
def drift_fix_offline(inputs: dict) -> dict:
    """Deterministic draft (the offline handler). A language model may only improve the wording of `explanation`."""
    change = {"renames": inputs.get("renames", []), "type_changes": inputs.get("type_changes", []),
              "added_columns": inputs.get("added_columns", []), "removed_columns": inputs.get("removed_columns", [])}
    return {"diff": build_diff(inputs["table"], change), "explanation": offline_explanation(inputs),
            "mapping": [{"from": r["from"], "to": r["to"]} for r in inputs.get("renames", [])]}


def draft_fix(change: Mapping[str, Any]) -> dict[str, Any] | None:
    """A drafted fix for a detected change, or None when no column changed."""
    if not change.get("changed"):
        return None
    from llm.client import complete_json

    table = change["table"]
    text = _model_text(table)
    already = bool(text) and any(r["to"] in text for r in change.get("renames", []))
    inputs = {k: change[k] for k in ("table", "added_columns", "removed_columns", "renames", "type_changes",
                                     "explanation_sources")} | {"model_already_reads_new": already,
                                                                "model_path": str(model_path(table))}
    res = complete_json("drift_fix", 1, inputs, "drift_fix")
    diff = build_diff(table, change, text)  # the diff is never taken from a model
    meta = res.get("_meta", {})
    return {"fix_id": f"FIX-{table}-{stable_hash([table, diff])[:8]}", "table": table,
            "description": describe(table, change), "diff": diff,
            "explanation": res.get("explanation") or offline_explanation(inputs),
            "status": PENDING, "applied": False,
            "drafted_by": ("rules" if meta.get("provider", "offline") == "offline"
                           else f"rules + {meta['provider']} wording"),
            "change": dict(change)}


# ------------------------------------------------------------------ the store
def _ready(con) -> None:
    con.executescript(SCHEMA)


def _row(r: Mapping[str, Any]) -> dict[str, Any]:
    d = dict(r)
    d["change"] = json.loads(d.pop("change_json"))
    d["applied"] = bool(d["applied"])
    d["table"] = d.pop("table_name")
    return d


def store_fix(fix: Mapping[str, Any]) -> bool:
    with ops() as con:
        _ready(con)
        cur = con.execute("INSERT OR IGNORE INTO drift_fixes (fix_id, table_name, change_json, description, diff, "
                          "explanation, status, applied, drafted_by) VALUES (?,?,?,?,?,?,?,0,?)",
                          (fix["fix_id"], fix["table"], json.dumps(fix["change"], default=str), fix["description"],
                           fix["diff"], fix["explanation"], PENDING, fix["drafted_by"]))
        return cur.rowcount > 0


def record(change: Mapping[str, Any]) -> dict[str, Any] | None:
    """Draft a fix for a detected change and store it as pending. Same change, same fix id: stored once."""
    fix = draft_fix(change)
    if fix:
        store_fix(fix)
    return fix


def fixes(status: str | None = None) -> list[dict[str, Any]]:
    with ops() as con:
        _ready(con)
        q = "SELECT * FROM drift_fixes" + (" WHERE status = ?" if status else "") + " ORDER BY created_ts, fix_id"
        return [_row(r) for r in con.execute(q, (status,) if status else ()).fetchall()]


def get_fix(fix_id: str) -> dict[str, Any] | None:
    with ops() as con:
        _ready(con)
        r = con.execute("SELECT * FROM drift_fixes WHERE fix_id = ?", (fix_id,)).fetchone()
    return _row(r) if r else None


def approve_fix(fix_id: str, user_id: str, role: str, note: str | None = None) -> dict[str, Any]:
    """The data steward approves a drafted fix. Audited. Nothing is applied: an engineer makes the change."""
    if str(role) not in APPROVERS:
        raise PermissionError(f"Only the data steward approves schema fixes, not the {role} role")
    fx = get_fix(fix_id)
    if fx is None:
        raise KeyError(fix_id)
    if fx["status"] != PENDING:
        raise ValueError(f"This fix has already been dealt with ({fx['status']})")
    audit_id = audit.record(user_id, role, "drift_fix_approve", "drift_fix", fix_id,
                            {"fix_id": fix_id, "table": fx["table"], "note": note},
                            {"status": "approved_by_engineer", "applied": False})
    with ops() as con:
        con.execute("UPDATE drift_fixes SET status='approved_by_engineer', decided_by=?, decision_note=?, "
                    "decided_ts=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE fix_id=?", (user_id, note, fix_id))
    return {"fix_id": fix_id, "status": "approved_by_engineer", "applied": False, "audit_id": audit_id,
            "note": "Approved. The app changes nothing: an engineer applies the mapping in the dbt project."}


# ------------------------------------------------------------------ the real warehouse (read only)
def scan_warehouse(con=None, days_before: int = 7, days_after: int = 7) -> list[dict[str, Any]]:
    """For each platform_release or data_feed_issue in ops_events that names a table we can slice by time, compare
    the week before it with the week from its start. Returns detections (changed or not), each with its drafted fix."""
    from common.db import warehouse

    own = con is None
    con = con or warehouse(read_only=True)
    try:
        events = [dict(zip(("event_id", "event_type", "description", "affected_tables", "start_ts"), r, strict=True))
                  for r in con.execute("SELECT event_id, event_type, description, affected_tables, start_ts "
                                       "FROM silver.ops_events WHERE event_type IN ('platform_release', "
                                       "'data_feed_issue') ORDER BY start_ts").fetchall()]
        notes = [dict(zip(("doc_id", "doc_type", "related_table"), r, strict=True)) for r in con.execute(
            "SELECT doc_id, doc_type, related_table FROM silver.reference_documents WHERE doc_type='release_note'"
        ).fetchall()]
        out = []
        for e in events:
            tables = json.loads(e["affected_tables"]) if str(e["affected_tables"]).startswith("[") else []
            for t in tables:
                if t not in TIME_COLUMNS:
                    continue
                s = e["start_ts"]
                base = profile_from_warehouse(con, t, s - dt.timedelta(days=days_before), s)
                new = profile_from_warehouse(con, t, s, s + dt.timedelta(days=days_after))
                change = detect(t, base, new, [e], notes)
                change["event_id"] = e["event_id"]
                change["event_description"] = e["description"]
                change["window"] = {"baseline_from": str(s - dt.timedelta(days=days_before)), "boundary": str(s),
                                    "new_to": str(s + dt.timedelta(days=days_after))}
                out.append(change)
        return out
    finally:
        if own:
            con.close()
