from fastapi import APIRouter, Depends, HTTPException

from api.deps import require
from api.schemas.assistant import Journey
from common.types import Role
from decisioning.assistant import journey as jr

router = APIRouter(prefix="/demo", tags=["demo"])
jr.prewarm()
EVERYONE = {Role.agent, Role.hardship_specialist, Role.team_lead, Role.analyst, Role.steward}


@router.get("/journey/{persona}")
def journey(persona: str, s=Depends(require(EVERYONE))) -> Journey:
    """The guided demo for the signed-in persona: one customer's decision journey with live
    evidence from the real tools. A person can only open the journey for their own role."""
    role = s.role.value if hasattr(s.role, "value") else str(s.role)
    if persona not in {r.value for r in Role}:
        raise HTTPException(404, "No such persona")
    if persona != role:
        raise HTTPException(403, detail={"reason": f"This guided demo is for the {persona.replace('_', ' ')} role."})
    return Journey.model_validate(jr.journey(persona))
