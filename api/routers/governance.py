from pathlib import Path

import yaml
from fastapi import APIRouter, Depends

from api.deps import require, stub
from common.types import Role
from governance import audit

router = APIRouter(prefix="/governance", tags=["governance"])
GOV = {Role.steward, Role.analyst, Role.team_lead}
CONTRACT = Path(__file__).resolve().parents[2] / "docs" / "contracts" / "c360_customer.v1.yaml"


@router.get("/quality")
def quality(s=Depends(require(GOV))):
    return stub("quality")


@router.get("/benchmark")
def benchmark(s=Depends(require(GOV))):
    return stub("benchmark")


@router.get("/monitoring")
def monitoring(s=Depends(require(GOV))):
    return stub("monitoring")


@router.get("/fairness")
def fairness(s=Depends(require(GOV))):
    return stub("fairness")


@router.get("/audit")
def audit_log(limit: int = 200, s=Depends(require({Role.steward, Role.team_lead}))):
    return {"items": audit.query(limit=limit)}


@router.get("/contract")
def contract(s=Depends(require(GOV))):
    return yaml.safe_load(CONTRACT.read_text())
