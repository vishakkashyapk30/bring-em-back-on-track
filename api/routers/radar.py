from fastapi import APIRouter, Depends

from api.deps import live_or_fixture, require, stub
from api.services import analytics
from common.types import Role

router = APIRouter(tags=["radar"])
WHO = {Role.team_lead, Role.analyst}


@router.get("/radar/employers")
def employers(week: str | None = None, s=Depends(require(WHO))):
    return stub("radar")


@router.get("/radar/employers/{key}")
def employer(key: str, s=Depends(require(WHO))):
    return stub("radar_detail")


@router.get("/map")
def bubble_map(metric: str = "broken_ptp_rate", level: str = "fsa", s=Depends(require(WHO))):
    """S2 weather map: metric by postal area (FSA centroid), areas under 10 customers suppressed."""
    return live_or_fixture("map", analytics.bubble_map, metric)
