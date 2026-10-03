from fastapi import APIRouter, Depends

from api.deps import require, stub
from api.schemas.nba import StressTestIn
from common.types import Role

router = APIRouter(tags=["team"])


@router.post("/stress-test")
def stress(body: StressTestIn, s=Depends(require({Role.team_lead, Role.analyst}))):
    return stub("stress_test")


@router.get("/scorecard")
def scorecard(s=Depends(require({Role.team_lead, Role.analyst}))):
    """S4 strategy scorecard; causal only for randomised cells."""
    return stub("scorecard")


@router.get("/team/agents")
def agents(s=Depends(require({Role.team_lead}))):
    return stub("agents")
