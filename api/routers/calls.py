from fastapi import APIRouter, Depends

from api.deps import require, stub
from common.types import Role

router = APIRouter(tags=["calls"])


@router.get("/calls/{contact_id}/summary")
def summary(contact_id: str, s=Depends(require({Role.agent}))):
    """Post-call draft with turn citations + promise mismatch flag (decisioning.post_call.draft)."""
    return stub("call_summary")


@router.post("/calls/{contact_id}/summary/approve")
def approve(contact_id: str, body: dict, s=Depends(require({Role.agent}))):
    raise NotImplementedError("TODO(WS-E): decisioning.post_call.approve")


@router.get("/calls/{contact_id}/transcript")
def transcript(contact_id: str, s=Depends(require({Role.agent, Role.hardship_specialist}))):
    return stub("transcript")
