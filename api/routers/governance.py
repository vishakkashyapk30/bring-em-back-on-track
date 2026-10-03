from pathlib import Path

import yaml
from fastapi import APIRouter, Depends

from api.deps import require, stub
from common.types import Role
from governance import audit

router = APIRouter(prefix="/governance", tags=["governance"])
GOV = {Role.steward, Role.analyst, Role.team_lead}
CONTRACT = Path(__file__).resolve().parents[2] / "docs" / "contracts" / "c360_customer.v1.yaml"


def _report(name: str, fixture_name: str):
    import json

    from common.config import get_settings

    p = get_settings().reports_dir / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else stub(fixture_name)


@router.get("/quality")
def quality(s=Depends(require(GOV))):
    """Data quality report (deliverable 4): regenerate with `make quality`."""
    return _report("data_quality", "quality")


@router.get("/benchmark")
def benchmark(s=Depends(require(GOV))):
    """Benchmark run (deliverable 5): regenerate with `make benchmark`."""
    return _report("benchmark", "benchmark")


@router.get("/features/parity")
def parity(s=Depends(require(GOV))):
    return _report("feature_parity", "monitoring")


@router.get("/monitoring")
def monitoring(s=Depends(require(GOV))):
    from api.deps import live_or_fixture
    from api.services import analytics

    return live_or_fixture("monitoring", analytics.monitoring)


@router.get("/fairness")
def fairness(s=Depends(require(GOV))):
    return stub("fairness")


@router.get("/audit")
def audit_log(limit: int = 200, s=Depends(require({Role.steward, Role.team_lead}))):
    return {"items": audit.query(limit=limit)}


@router.get("/contract")
def contract(s=Depends(require(GOV))):
    return yaml.safe_load(CONTRACT.read_text())
