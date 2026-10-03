from fastapi import APIRouter, Depends

from api.deps import live_data, require, stub
from api.schemas.nba import PolicyQuestionIn
from common.types import Role

router = APIRouter(tags=["assist"])


@router.post("/assist/policy")
def policy(body: PolicyQuestionIn, s=Depends(require({Role.agent, Role.hardship_specialist}))):
    """Cited policy answer or refusal: current documents only, ranked by authority (rag/)."""
    if not live_data():
        return stub("assist_policy")
    from rag.answer import answer_question

    return {"meta": {"fixture": False}, **answer_question(body.question)}


@router.get("/assist/prompts/{contact_id}")
def prompts(contact_id: str, s=Depends(require({Role.agent}))):
    return stub("assist_prompts")
