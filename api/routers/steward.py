from fastapi import APIRouter, Depends

from api.deps import require, stub
from api.schemas.nba import IdentityVerdictIn
from common.types import Role

router = APIRouter(prefix="/steward", tags=["steward"])


@router.get("/identity/queue")
def queue(s=Depends(require({Role.steward}))):
    return stub("identity_queue")


@router.post("/identity/{pair_id}")
def verdict(pair_id: str, body: IdentityVerdictIn, s=Depends(require({Role.steward}))):
    raise NotImplementedError("TODO(WS-A/WS-F): write identity_reviews + audit")
