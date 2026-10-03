from fastapi import APIRouter, Depends

from api.deps import require
from api.schemas.assistant import AssistantRun, AssistantRunIn, Suggestions
from common.types import Role
from decisioning.assistant import plans, runner

router = APIRouter(prefix="/assistant", tags=["assistant"])
EVERYONE = {Role.agent, Role.hardship_specialist, Role.team_lead, Role.analyst, Role.steward}


@router.get("/suggestions")
def suggestions(s=Depends(require(EVERYONE))) -> Suggestions:
    """The goals that work for the signed-in persona; each one is checked by tests/unit/test_assistant.py."""
    role = s.role.value if hasattr(s.role, "value") else str(s.role)
    ps = plans.plans_for(role)
    return Suggestions.model_validate({
        "persona": role,
        "briefing": {"label": ps[0].label, "goal": ps[0].goal},
        "goals": [{"label": p.label, "goal": p.goal} for p in ps[1:] if p.label]})


@router.post("/run")
def run(body: AssistantRunIn, s=Depends(require(EVERYONE))) -> AssistantRun:
    """Plan, call real tools, show every step with its evidence, and propose actions a person approves in the existing
    screens. Read-only: the assistant never changes customer data or contacts anyone. Every run is audited."""
    return AssistantRun.model_validate(runner.run(s, body.goal, body.case_id, body.golden_id, body.mode))
