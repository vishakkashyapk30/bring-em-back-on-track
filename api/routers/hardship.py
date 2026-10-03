from fastapi import APIRouter, Depends, HTTPException

from api.deps import live_data, require, stub
from api.schemas.common import WriteResult
from api.schemas.nba import HardshipFlagIn, SimulatorIn
from api.services import hardship as hardship_svc
from common.types import HardshipLevel, Role
from governance import audit, hardship_latch

router = APIRouter(tags=["hardship"])
SPECIALIST = {Role.hardship_specialist}


@router.post("/hardship/{golden_id}/flag")
def flag(
    golden_id: str, body: HardshipFlagIn, s=Depends(require({Role.agent, Role.hardship_specialist}))
) -> WriteResult:
    current = HardshipLevel(hardship_svc.current_level(golden_id)) if live_data() else HardshipLevel.none
    source = "specialist" if s.role == Role.hardship_specialist else "agent_coded"
    try:
        audit_id = hardship_latch.transition(
            golden_id, current, HardshipLevel(body.target), source, s.user_id, s.role, body.reason, body.program_id
        )
    except hardship_latch.LatchError as e:
        raise HTTPException(403, detail={"reason": str(e)}) from e
    return WriteResult(audit_id=audit_id)


@router.get("/hardship/board")
def board(s=Depends(require(SPECIALIST))):
    """Customers flagged 'possible' waiting for a person to confirm or clear, oldest overdue first."""
    return hardship_svc.board() if live_data() else stub("hardship_board")


@router.get("/hardship/missed-offers")
def missed(s=Depends(require(SPECIALIST))):
    return hardship_svc.missed_offers() if live_data() else stub("missed_offers")


@router.get("/hardship/overrides")
def overrides(s=Depends(require(SPECIALIST))):
    return hardship_svc.overrides() if live_data() else stub("overrides")


@router.post("/simulator/{case_id}")
def simulate(case_id: str, body: SimulatorIn, s=Depends(require(SPECIALIST))):
    """H1 (decisioning.simulator.simulate); every run is logged."""
    if not live_data():
        return stub("simulator")
    import json

    from api.services.c360 import _meta
    from common.db import ops
    from decisioning import simulator

    levers = body.model_dump()
    out = simulator.simulate(case_id, levers)
    if out is None:
        raise HTTPException(404, "No open case with that ID")
    if out.get("error"):
        raise HTTPException(422, out["error"])
    audit_id = audit.record(s.user_id, s.role, "simulator_run", "case", case_id, levers, out["results"])
    with ops() as con:
        con.execute(
            "INSERT INTO simulator_runs (case_id, user_id, levers_json, result_json) VALUES (?,?,?,?)",
            (case_id, s.user_id, json.dumps(levers), json.dumps(out, default=str)),
        )
    return {"meta": _meta(), **out, "audit_id": audit_id}
