from fastapi import APIRouter, Depends

from api import access
from api.deps import live_data, require, stub
from api.schemas.common import WriteResult
from api.schemas.nba import DecisionIn, WhatIfIn
from common.types import Role
from governance import audit

router = APIRouter(tags=["nba"])


@router.get("/nba/{case_id}")
def proposal(case_id: str, s=Depends(require({Role.agent, Role.hardship_specialist, Role.team_lead}))):
    """Proposed action + full explanation + alternatives (decisioning.nba.propose), recomputed live."""
    if not live_data():
        return stub("nba")
    from fastapi import HTTPException

    from api.services import nba as svc

    access.case(s, case_id)
    p = svc.proposal(case_id, s)
    if p is None:
        raise HTTPException(404, "No open case with that ID")
    return p


@router.post("/nba/{case_id}/decision")
def decide(case_id: str, body: DecisionIn, s=Depends(require({Role.agent, Role.hardship_specialist}))) -> WriteResult:
    """Approve / edit / override. Override needs a reason code; an edit carries the action the person chose."""
    from fastapi import HTTPException

    if body.decision == "override" and not body.reason_code:
        raise HTTPException(422, "Override needs a reason code")
    if body.decision == "edit" and body.action is None:
        raise HTTPException(422, "An edit needs the action you chose")
    if not live_data():
        return WriteResult(audit_id=audit.record(s.user_id, s.role, "nba_decision", "case", case_id, body.model_dump()))
    from api.services import nba as svc

    access.case(s, case_id)
    try:
        return WriteResult(audit_id=svc.record_decision(s, case_id, body))
    except KeyError as e:
        raise HTTPException(404, "No open case with that ID") from e
    except ValueError as e:
        raise HTTPException(403, detail={"reason": str(e)}) from e


@router.post("/nba/what-if")
def what_if(body: WhatIfIn, s=Depends(require({Role.agent, Role.hardship_specialist}))):
    """A2 promise what-if; response carries the label 'model estimate, not cause and effect'. Saves nothing."""
    if not live_data():
        return stub("what_if")
    from decisioning.promise_check import what_if as run

    access.case(s, body.case_id)
    out = run(body.case_id, body.ptp_amount, body.ptp_due_date, body.split)
    from api.services.c360 import _meta

    return {"meta": _meta(), **out}


@router.get("/eligibility/{case_id}")
def eligibility(case_id: str, s=Depends(require({Role.agent, Role.hardship_specialist}))):
    """Every program for the case's product, checked rule by rule. Rules decide, never an LLM."""
    if not live_data():
        return stub("eligibility")
    from fastapi import HTTPException

    from api.services.c360 import _meta
    from decisioning import eligibility as elig

    access.case(s, case_id)

    out = elig.check(case_id)
    if out is None:
        raise HTTPException(404, "No open case with that ID")
    return {"meta": _meta(), **out}
