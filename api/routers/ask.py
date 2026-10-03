from fastapi import APIRouter, Depends

from api.deps import require, stub
from api.schemas.nba import AskIn
from common.types import Role
from nlq import refusal
from nlq.schemas import AskResponse

router = APIRouter(tags=["ask"])


@router.post("/ask")
def ask(body: AskIn, s=Depends(require({Role.analyst, Role.team_lead, Role.agent}))) -> AskResponse:
    """Real: nlq.pipeline.ask(question, role, user_id). Refusal check already live."""
    reason = refusal.check(body.question, None)
    if reason:
        from governance import audit

        audit.record(s.user_id, s.role, "refusal", "question", None, {"q": body.question}, reason)
        return AskResponse(question=body.question, refused=True, refusal_reason=reason)
    return AskResponse.model_validate({**stub("ask"), "question": body.question})
