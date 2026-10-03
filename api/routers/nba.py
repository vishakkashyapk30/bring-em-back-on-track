from fastapi import APIRouter, Depends

from api.deps import require, stub
from api.schemas.common import WriteResult
from api.schemas.nba import DecisionIn, WhatIfIn
from common.types import Role
from governance import audit

router = APIRouter(tags=["nba"])


@router.get("/nba/{case_id}")
def proposal(case_id: str, s=Depends(require({Role.agent, Role.hardship_specialist, Role.team_lead}))):
    """Proposed action + full explanation + alternatives (decisioning.nba.propose)."""
    return stub("nba")


@router.post("/nba/{case_id}/decision")
def decide(case_id: str, body: DecisionIn,
           s=Depends(require({Role.agent, Role.hardship_specialist}))) -> WriteResult:
    """Approve / edit / override. Override needs a reason code. TODO(WS-F): write nba_decisions row."""
    if body.decision == "override" and not body.reason_code:
        from fastapi import HTTPException

        raise HTTPException(422, "Override needs a reason code")
    audit_id = audit.record(s.user_id, s.role, "nba_decision", "case", case_id, body.model_dump())
    return WriteResult(audit_id=audit_id)


@router.post("/nba/what-if")
def what_if(body: WhatIfIn, s=Depends(require({Role.agent, Role.hardship_specialist}))):
    """A2 promise what-if; response must carry label 'model estimate, not cause and effect'."""
    return stub("what_if")


@router.get("/eligibility/{case_id}")
def eligibility(case_id: str, s=Depends(require({Role.agent, Role.hardship_specialist}))):
    return stub("eligibility")
