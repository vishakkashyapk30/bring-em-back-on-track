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
from governance import audit
from llm.providers.offline import register


def _transcript(con, where: str, params: list) -> tuple | None:
    return con.execute(
        f"""SELECT t.transcript_id, t.contact_id, t.case_id, t.call_start_ts, t.file_path, t.language,
                   p.ptp_amount, p.ptp_due_date, t.asr_confidence_avg
            FROM silver.call_transcripts t
            LEFT JOIN silver.promises_to_pay p ON p.contact_id = t.contact_id
            WHERE {where} ORDER BY t.call_start_ts DESC LIMIT 1""", params).fetchone()


def summarise(contact_id: str | None = None, case_id: str | None = None) -> dict | None:
    """The draft for the latest call of a contact or case, from the warehouse and the transcript file."""
    con = warehouse(read_only=True)
    try:
        row = (_transcript(con, "t.contact_id = ?", [contact_id]) if contact_id
               else _transcript(con, "t.case_id = ?", [case_id]))
    finally:
        con.close()
    if not row:
        return None
    tid, cid, case, start, path, lang, amount, due, asr = row
    turns = json.loads((get_settings().raw_dir / "maple_collections_release" / "files" / path).read_text())["turns"]
    record = {"amount": amount, "date": due.isoformat() if hasattr(due, "isoformat") else due} if amount else None
    call_date = start.date() if hasattr(start, "date") else date.fromisoformat(str(start)[:10])
    d = draft_from_turns(turns, call_date, record, asr)
    return {"transcript_id": tid, "contact_id": cid, "case_id": case, "call_start_ts": str(start), "language": lang,
            "fields": d["fields"], "summary": d["summary"], "turns": turns, "checks": d["checks"],
            "evidence": d["evidence"], "payload": d["payload"]}


def draft_from_turns(turns: list[dict], call_date: date | None = None, record: dict | None = None,
                     asr_confidence_avg: float | None = None) -> dict:
    """The draft for one call: fields (the recorded promise wins when there is one), the template summary, a check
    that the transcript's promise agrees with the record (highlighted, never silently fixed), the turn citations,
    and the schema-shaped payload (llm/schemas/post_call_summary.json) with its validation result. The recorded
    promise stays the default; the payload also carries what the call said (`in_transcript`) and a `mismatch` flag
    so the agent sees both. A call whose ASR confidence is below the floor gets its text features marked missing."""
    fields = extract(turns, call_date, record, asr_confidence_avg)
    from_text = extract(turns, call_date, None, asr_confidence_avg)
    said, rec = from_text.get("ptp") or {}, record or {}
    mismatch = bool(record and said.get("amount") is not None and (
        abs(float(said["amount"]) - float(rec["amount"])) > 0.5
        or (said.get("date") and rec.get("date") and str(said["date"])[:10] != str(rec["date"])[:10])))
    payload = _payload(fields)
    if payload["promise"] is not None or said:
        payload["promise"] = {**(payload["promise"] or {"amount": None, "date": None, "ptp_intent_strength": None,
                                                         "turns": []}),
                              "recorded": ({"amount": rec["amount"], "date": str(rec["date"])[:10]}
                                           if record else None),
                              "in_transcript": said or None, "mismatch": mismatch}
    return {"fields": fields, "summary": summary(fields), "evidence": fields["cites"], "payload": payload,
            "schema_valid": _schema_ok(payload),
            "checks": {"promise_matches_record": not mismatch, "promise_from": "record" if record else "transcript",
                       "promise_in_transcript": said or None}}


def _payload(f: dict) -> dict:
    c = f["cites"]
    promise = None
    if f.get("ptp"):
        promise = {"amount": f["ptp"]["amount"], "date": f["ptp"]["date"],
                   "ptp_intent_strength": f.get("ptp_intent_strength"),
                   "turns": c["promise"]}
    return {"summary": {"text": summary(f), "turns": sorted({t for v in c.values() for t in v})}, "promise": promise,
            "signals": {"hardship_signal": f["hardship"], "stated_delay_reason": f["stated_delay_reason"],
                        "dispute_signal": f["dispute"], "complaint_cue": f["complaint"],
                        "vulnerability_cue": False, "low_confidence": bool(f.get("low_confidence")),
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


APPROVER_ROLES = ("agent", "hardship_specialist")


def _flat(d: dict) -> dict:
    """Top-level fields of a draft with the signals spread out, so an edit to one signal is one edited field."""
    out = {k: v for k, v in d.items() if k != "signals"}
    out.update(d.get("signals") or {})
    return out


def approve(contact_id: str, approved: dict, user_id: str, role: str = "agent", original: dict | None = None,
            assigned_to: str | None = None, provider: str = "offline", prompt_version: str = "rules-v1",
            draft_id: str | None = None) -> dict:
    """An agent approves (and may have edited) the draft for a contact. Only approved values are saved: the approved
    draft and the original draft go to ops.db call_summaries, the edited fields are listed, and the approval is
    written through governance.audit.record. Only a person in an approver role, and (when `assigned_to` is given)
    only the agent assigned to the case, may approve. The audit row is keyed by `draft_id` when the caller has one, else
    the contact. Returns {audit_id, approved_by, saved_fields, edited_fields}."""
    import json

    from common.db import ops

    if role not in APPROVER_ROLES or not user_id:
        raise PermissionError("Only a person (the assigned agent or a hardship specialist) can approve a summary")
    if assigned_to is not None and role == "agent" and assigned_to != user_id:
        raise PermissionError("Only the agent assigned to this case can approve its summary")
    original = original if original is not None else approved
    before, after = _flat(original), _flat(approved)
    edited = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    saved = after
    audit_id = audit.record(user_id, role, "summary_approve", "contact", draft_id or contact_id,
                            {"edited_fields": edited, "original": original}, {"approved": approved})
    with ops() as con:
        con.execute("""INSERT INTO call_summaries (contact_id, draft_json, approved_json, status, edited_fields,
                       prompt_version, provider, approved_by, approved_ts)
                       VALUES (?, ?, ?, 'approved', ?, ?, ?, ?, datetime('now'))
                       ON CONFLICT(contact_id) DO UPDATE SET draft_json = excluded.draft_json,
                       approved_json = excluded.approved_json, status = 'approved',
                       edited_fields = excluded.edited_fields, prompt_version = excluded.prompt_version,
                       provider = excluded.provider, approved_by = excluded.approved_by,
                       approved_ts = excluded.approved_ts""",
                    (contact_id, json.dumps(original, default=str), json.dumps(approved, default=str),
                     json.dumps(edited), prompt_version, provider, user_id))
    return {"audit_id": audit_id, "approved_by": user_id, "saved_fields": saved, "edited_fields": edited}


def raise_hardship_from_approval(golden_id: str, approved: dict, user_id: str) -> int | None:
    """An approved summary that carries a hardship cue raises the latch to `possible` (a rule raise: rules may raise,
    never lower or confirm). Returns the audit id, or None when there is no cue or the flag is already at least
    `possible`. Pressure actions stop at once because the NBA reads the latch from ops.db."""
    from common.db import ops
    from governance import hardship_latch

    signal = ((approved.get("signals") or {}).get("hardship_signal")) or "none"
    if signal not in ("possible", "clear"):
        return None
    with ops() as con:
        r = con.execute("SELECT to_level FROM hardship_flag_events WHERE golden_id = ? ORDER BY event_id DESC LIMIT 1",
                        (golden_id,)).fetchone()
    if r is not None:
        current = r["to_level"]
    else:
        try:
            from api.services.hardship import current_level

            current = current_level(golden_id)
        except Exception:  # noqa: BLE001 - no warehouse: nothing on record means none
            current = "none"
    if current != "none":
        return None
    return hardship_latch.transition(golden_id, "none", "possible", "rule", "post_call_summary_rule", "system",
                                     f"hardship cue in the approved call summary (approved by {user_id})")
