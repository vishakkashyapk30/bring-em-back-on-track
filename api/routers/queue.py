from fastapi import APIRouter, Depends

from api.deps import require, stub
from common.types import Role

router = APIRouter(tags=["queue"])


@router.get("/queue")
def get_queue(date: str | None = None, s=Depends(require({Role.agent, Role.team_lead}))):
    """Today's NBA queue. Real: decisioning.nba.build_queue(date) filtered to the agent/team."""
    return stub("queue")


@router.get("/batches")
def batches(status: str = "pending", s=Depends(require({Role.team_lead}))):
    return stub("batches")


@router.post("/batches/{batch_id}/approve")
def approve_batch(batch_id: str, s=Depends(require({Role.team_lead}))):
    raise NotImplementedError("TODO(WS-F): mark approved + audit")
