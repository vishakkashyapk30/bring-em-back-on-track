from fastapi import APIRouter, Depends

from api.deps import require, stub
from common.types import Role

router = APIRouter(tags=["customers"])
VIEWERS = {Role.agent, Role.hardship_specialist, Role.team_lead, Role.steward}


@router.get("/customers/{golden_id}")
def customer(golden_id: str, s=Depends(require(VIEWERS))):
    """C360: header badges, holdings, identity & lineage, freshness. Agents: own cases only (TODO)."""
    return stub("customer")


@router.get("/customers/{golden_id}/timeline")
def timeline(golden_id: str, cursor: str | None = None, s=Depends(require(VIEWERS))):
    return stub("timeline")


@router.get("/customers/{golden_id}/identity")
def identity(golden_id: str, s=Depends(require(VIEWERS))):
    return stub("identity")


@router.get("/features/online/{golden_id}", tags=["features"])
def online_vector(golden_id: str, s=Depends(require({Role.analyst, Role.steward, Role.agent}))):
    return stub("features_online")
