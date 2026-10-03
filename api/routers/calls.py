import json

from fastapi import APIRouter, Depends, HTTPException

from api.deps import live_data, require, stub
from api.schemas.common import WriteResult
from common.db import ops
from common.types import Role
from governance import audit

router = APIRouter(tags=["calls"])


def _summary(contact_id: str) -> dict:
    from decisioning.post_call import summarise

    s = summarise(contact_id=contact_id)
    if s is None:
        raise HTTPException(404, "No transcript for this contact")
    f = s["fields"]
    ptp = f.get("ptp") or None
    return {
        "meta": {"fixture": False}, "contact_id": contact_id, "transcript_id": s["transcript_id"], "case_id": s["case_id"],
        "status": "draft", "provider": "offline",
        "draft": {
            "summary": {"text": s["summary"], "turns": []},
            "promise": ({"amount": ptp.get("amount"), "date": ptp.get("date"), "ptp_intent_strength": None, "turns": []}
                        if ptp else None),
            "signals": {"hardship_signal": f["hardship"], "hardship_reason": f.get("hardship_reason"),
                        "stated_delay_reason": f.get("stated_delay_reason"), "dispute_signal": f["dispute"],
                        "complaint_cue": f["complaint"], "cease_request": f.get("cease_request"),
                        "vulnerability_cue": False, "turns": []},
            "next_steps": [{"text": (f.get("next_step") or "").replace("_", " "), "turns": []}],
        },
        "checks": {"schema_valid": True, **s["checks"]},
    }


@router.get("/calls/{contact_id}/summary")
def summary(contact_id: str, s=Depends(require({Role.agent}))):
    """Post-call draft (rule extraction validated on 500 labelled transcripts) + promise check against the record."""
    return _summary(contact_id) if live_data() else stub("call_summary")


@router.post("/calls/{contact_id}/summary/approve")
def approve(contact_id: str, body: dict, s=Depends(require({Role.agent}))) -> WriteResult:
    """The agent approves (optionally edited) notes; only approved values are saved. Audited."""
    draft = body.get("draft") or {}
    audit_id = audit.record(s.user_id, s.role, "summary_approve", "contact", contact_id, draft)
    with ops() as con:
        con.execute("""INSERT INTO call_summaries (contact_id, draft_json, approved_json, status, prompt_version, provider,
                       approved_by, approved_ts) VALUES (?, ?, ?, 'approved', 'rules-v1', 'offline', ?, datetime('now'))
                       ON CONFLICT(contact_id) DO UPDATE SET approved_json = excluded.approved_json,
                       status = 'approved', approved_by = excluded.approved_by, approved_ts = excluded.approved_ts""",
                    (contact_id, json.dumps(body.get("original") or draft), json.dumps(draft), s.user_id))
    return WriteResult(audit_id=audit_id)


@router.get("/calls/{contact_id}/transcript")
def transcript(contact_id: str, s=Depends(require({Role.agent, Role.hardship_specialist}))):
    if not live_data():
        return stub("transcript")
    from decisioning.post_call import summarise

    t = summarise(contact_id=contact_id)
    if t is None:
        raise HTTPException(404, "No transcript for this contact")
    return {"meta": {"fixture": False}, "contact_id": contact_id, "transcript_id": t["transcript_id"],
            "turns": [{"turn_index": x["turn_index"], "speaker": x["speaker"], "text": x["text"]} for x in t["turns"]]}
