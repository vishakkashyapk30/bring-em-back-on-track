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
    from common.llm_mode import use_mode
    from rag.answer import answer_with_llm

    with use_mode(body.mode):
        out = answer_with_llm(body.question)
    return {"meta": {"fixture": False}, "answered_by": "language model" if out.get("by_llm") else "rules", **out}


@router.get("/assist/prompts/{contact_id}")
def prompts(contact_id: str, s=Depends(require({Role.agent}))):
    return stub("assist_prompts")
