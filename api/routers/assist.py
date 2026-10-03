from fastapi import APIRouter, Depends

from api.deps import require, stub
from api.schemas.nba import PolicyQuestionIn
from common.types import Role

router = APIRouter(tags=["assist"])


@router.post("/assist/policy")
def policy(body: PolicyQuestionIn, s=Depends(require({Role.agent, Role.hardship_specialist}))):
    """Cited policy answer or refusal (decisioning.assist.policy_answer)."""
    return stub("assist_policy")


@router.get("/assist/prompts/{contact_id}")
def prompts(contact_id: str, s=Depends(require({Role.agent}))):
    return stub("assist_prompts")
