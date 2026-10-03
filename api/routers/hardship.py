from fastapi import APIRouter, Depends, HTTPException

from api.deps import require, stub
from api.schemas.common import WriteResult
from api.schemas.nba import HardshipFlagIn, SimulatorIn
from common.types import HardshipLevel, Role
from governance import hardship_latch

router = APIRouter(tags=["hardship"])
SPECIALIST = {Role.hardship_specialist}


@router.post("/hardship/{golden_id}/flag")
def flag(golden_id: str, body: HardshipFlagIn,
         s=Depends(require({Role.agent, Role.hardship_specialist}))) -> WriteResult:
    current = HardshipLevel.none  # TODO(WS-F): read current level from gold/ops
    source = "specialist" if s.role == Role.hardship_specialist else "agent_coded"
    try:
        audit_id = hardship_latch.transition(golden_id, current, HardshipLevel(body.target), source,
                                             s.user_id, s.role, body.reason, body.program_id)
    except hardship_latch.LatchError as e:
        raise HTTPException(403, detail={"reason": str(e)}) from e
    return WriteResult(audit_id=audit_id)


@router.get("/hardship/board")
def board(s=Depends(require(SPECIALIST))):
    return stub("hardship_board")


@router.get("/hardship/missed-offers")
def missed(s=Depends(require(SPECIALIST))):
    return stub("missed_offers")


@router.get("/hardship/overrides")
def overrides(s=Depends(require(SPECIALIST))):
    return stub("overrides")


@router.post("/simulator/{case_id}")
def simulate(case_id: str, body: SimulatorIn, s=Depends(require(SPECIALIST))):
    """H1 (decisioning.simulator.simulate); every run is logged."""
    return stub("simulator")
