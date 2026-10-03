from fastapi import APIRouter, Depends

from api.deps import live_or_fixture, require, stub
from api.schemas.nba import StressTestIn
from api.services import analytics
from common.types import Role

router = APIRouter(tags=["team"])


@router.post("/stress-test")
def stress(body: StressTestIn, s=Depends(require({Role.team_lead, Role.analyst}))):
    return stub("stress_test")


@router.get("/scorecard")
def scorecard(s=Depends(require({Role.team_lead, Role.analyst}))):
    """S4 strategy scorecard; causal only for randomised cells."""
    return live_or_fixture("scorecard", analytics.scorecard)


@router.get("/team/agents")
def agents(s=Depends(require({Role.team_lead}))):
    return live_or_fixture("agents", analytics.agents)
