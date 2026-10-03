from fastapi import APIRouter, Depends, HTTPException

from api import access
from api.deps import live_data, require, stub
from api.schemas.common import WriteResult
from common.types import Role

router = APIRouter(tags=["calls"])


def _summary(contact_id: str) -> dict:
    from decisioning.post_call import summarise

    s = summarise(contact_id=contact_id)
    if s is None:
        raise HTTPException(404, "No transcript for this contact")
    f, d = s["fields"], s["payload"]
    d["signals"] = {**d["signals"], "hardship_reason": f.get("hardship_reason"), "cease_request": f.get("cease_request")}
    return {
        "meta": {"fixture": False}, "contact_id": contact_id, "transcript_id": s["transcript_id"], "case_id": s["case_id"],
        "status": "draft", "provider": "offline", "draft": d,
        "checks": {"schema_valid": True, **s["checks"]},
    }


@router.get("/calls/{contact_id}/summary")
def summary(contact_id: str, s=Depends(require({Role.agent}))):
    """Post-call draft (rule extraction validated on 500 labelled transcripts) + promise check against the record."""
    access.contact(s, contact_id)
    return _summary(contact_id) if live_data() else stub("call_summary")


@router.post("/calls/{contact_id}/summary/approve")
def approve(contact_id: str, body: dict, s=Depends(require({Role.agent}))) -> WriteResult:
    """The agent approves (optionally edited) notes; only approved values are saved. Audited."""
    access.contact(s, contact_id)
    from decisioning.post_call import approve as approve_summary

    draft = body.get("draft") or {}
    try:
        res = approve_summary(contact_id, draft, s.user_id, s.role.value if hasattr(s.role, "value") else str(s.role),
                              original=body.get("original"))
    except PermissionError as e:
        raise HTTPException(403, str(e)) from e
    return WriteResult(audit_id=res["audit_id"])


@router.get("/calls/{contact_id}/transcript")
def transcript(contact_id: str, s=Depends(require({Role.agent, Role.hardship_specialist}))):
    access.contact(s, contact_id)
    if not live_data():
        return stub("transcript")
    from decisioning.post_call import summarise

    t = summarise(contact_id=contact_id)
    if t is None:
        raise HTTPException(404, "No transcript for this contact")
    return {"meta": {"fixture": False}, "contact_id": contact_id, "transcript_id": t["transcript_id"],
            "turns": [{"turn_index": x["turn_index"], "speaker": x["speaker"], "text": x["text"]} for x in t["turns"]]}
