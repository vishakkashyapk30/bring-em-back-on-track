from fastapi import APIRouter, Depends, HTTPException

from api.deps import live_data, require, stub
from api.schemas.common import WriteResult
from api.services import nba as svc
from common.types import Role

router = APIRouter(tags=["queue"])


@router.get("/queue")
def get_queue(date: str | None = None, view: str = "all", sort: str = "priority", q: str = "", offset: int = 0,
              limit: int = 50, s=Depends(require({Role.agent, Role.team_lead, Role.hardship_specialist}))):
    """Today's NBA queue for the signed-in person (agent: own cases; lead: the team; specialist: hardship cases)."""
    if not live_data():
        return stub("queue")
    return svc.queue(s, view, sort, q, max(offset, 0), min(max(limit, 1), 200))


@router.get("/batches")
def batches(status: str = "pending", s=Depends(require({Role.team_lead}))):
    if not live_data():
        return stub("batches")
    return svc.batches(status, s.team_id)


@router.post("/batches/{batch_id}/approve")
def approve_batch(batch_id: str, s=Depends(require({Role.team_lead}))) -> WriteResult:
    try:
        return WriteResult(audit_id=svc.approve_batch(s, batch_id))
    except KeyError as e:
        raise HTTPException(404, "No such batch") from e
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
