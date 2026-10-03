"""Supporting service A: post-call summaries (§11.3 of the build plan). Draft from the redacted transcript with
the offline extractor (features/text_rules.py, validated on the 500 public labels); the promise is taken from
the promises_to_pay row created on that contact when one exists (and flagged if the transcript disagrees).
The agent approves before anything is saved."""

from __future__ import annotations

import json
from datetime import date

from common.config import get_settings
from common.db import warehouse
from features.text_rules import extract, summary
from llm.providers.offline import register


def _transcript(con, where: str, params: list) -> tuple | None:
    return con.execute(
        f"""SELECT t.transcript_id, t.contact_id, t.case_id, t.call_start_ts, t.file_path, t.language,
                   p.ptp_amount, p.ptp_due_date
            FROM silver.call_transcripts t
            LEFT JOIN silver.promises_to_pay p ON p.contact_id = t.contact_id
            WHERE {where} ORDER BY t.call_start_ts DESC LIMIT 1""", params).fetchone()


def summarise(contact_id: str | None = None, case_id: str | None = None) -> dict | None:
    con = warehouse(read_only=True)
    try:
        row = (_transcript(con, "t.contact_id = ?", [contact_id]) if contact_id
               else _transcript(con, "t.case_id = ?", [case_id]))
    finally:
        con.close()
    if not row:
        return None
    tid, cid, case, start, path, lang, amount, due = row
    turns = json.loads((get_settings().raw_dir / "maple_collections_release" / "files" / path).read_text())["turns"]
    record = {"amount": amount, "date": due.isoformat() if hasattr(due, "isoformat") else due} if amount else None
    call_date = start.date() if hasattr(start, "date") else date.fromisoformat(str(start)[:10])
    d = draft_from_turns(turns, call_date, record)
    return {"transcript_id": tid, "contact_id": cid, "case_id": case, "call_start_ts": str(start), "language": lang,
            "fields": d["fields"], "summary": d["summary"], "turns": turns, "checks": d["checks"],
            "evidence": d["evidence"]}


def draft_from_turns(turns: list[dict], call_date: date | None = None, record: dict | None = None) -> dict:
    """The draft for one call: fields (the recorded promise wins when there is one), the template summary, a check
    that the transcript's promise agrees with the record (highlighted, never silently fixed), the turn citations,
    and the schema-shaped payload (llm/schemas/post_call_summary.json) with its validation result."""
    fields = extract(turns, call_date, record)
    from_text = extract(turns, call_date)
    said, rec = from_text.get("ptp") or {}, record or {}
    mismatch = bool(record and said.get("amount") is not None and (
        abs(float(said["amount"]) - float(rec["amount"])) > 0.5
        or (said.get("date") and rec.get("date") and str(said["date"])[:10] != str(rec["date"])[:10])))
    payload = _payload(fields)
    return {"fields": fields, "summary": summary(fields), "evidence": fields["cites"], "payload": payload,
            "schema_valid": _schema_ok(payload),
            "checks": {"promise_matches_record": not mismatch, "promise_from": "record" if record else "transcript",
                       "promise_in_transcript": said or None}}


def _payload(f: dict) -> dict:
    c = f["cites"]
    promise = None
    if f.get("ptp"):
        promise = {"amount": f["ptp"]["amount"], "date": f["ptp"]["date"], "ptp_intent_strength": None,
                   "turns": c["promise"]}
    return {"summary": {"text": summary(f), "turns": sorted({t for v in c.values() for t in v})}, "promise": promise,
            "signals": {"hardship_signal": f["hardship"], "stated_delay_reason": f["stated_delay_reason"],
                        "dispute_signal": f["dispute"], "complaint_cue": f["complaint"],
                        "vulnerability_cue": False,
                        "turns": sorted(set(c["hardship_signal"] + c["dispute_signal"] + c["complaint"]))},
            "next_steps": [{"text": f["next_step"].replace("_", " "), "turns": c["next_steps"]}]}


def _schema_ok(payload: dict) -> bool:
    import jsonschema

    from llm.client import load_schema

    try:
        jsonschema.validate(payload, load_schema("post_call_summary"))
    except jsonschema.ValidationError:
        return False
    return True


@register("post_call_summary")
def summary_offline(inputs: dict) -> dict:
    return _payload(extract(inputs.get("turns", [])))


def draft(contact_id: str) -> dict | None:
    return summarise(contact_id=contact_id)


def approve(contact_id: str, edited: dict, user_id: str) -> int:
    raise NotImplementedError("TODO(WS-E): write call_summaries + audit")
