from fastapi import APIRouter, Depends

from api import access
from api.deps import live_or_fixture, require
from api.services import c360
from common.types import Role

router = APIRouter(tags=["customers"])
VIEWERS = {Role.agent, Role.hardship_specialist, Role.team_lead, Role.steward}


@router.get("/customers/{golden_id}")
def customer(golden_id: str, s=Depends(require(VIEWERS))):
    """C360: header badges, holdings, consent, hardship and freshness, from gold.c360_customer / c360_account."""
    access.golden(s, golden_id)
    return live_or_fixture("customer", c360.customer, golden_id)


@router.get("/customers/{golden_id}/timeline")
def timeline(golden_id: str, cursor: str | None = None, s=Depends(require(VIEWERS))):
    access.golden(s, golden_id)
    return live_or_fixture("timeline", c360.timeline, golden_id)


@router.get("/customers/{golden_id}/identity")
def identity(golden_id: str, s=Depends(require(VIEWERS))):
    """Every source key linked to this golden ID, with method and confidence (identity.identity_xref).
    Open to stewards (lineage only); other roles follow their row scope."""
    access.lineage(s, golden_id)
    return live_or_fixture("identity", c360.identity, golden_id)


FEATURE_VIEWERS = {Role.analyst, Role.steward, Role.agent, Role.hardship_specialist}


@router.get("/features/online/{golden_id}", tags=["features"])
def online_vector(golden_id: str, s=Depends(require(FEATURE_VIEWERS))):
    """The customer's online feature vector (features.f_customer_online), same definitions as training."""
    if s.role in ("agent", "hardship_specialist"):
        access.golden(s, golden_id)
    return live_or_fixture("features_online", c360.features_online, golden_id)
