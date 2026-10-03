from fastapi import APIRouter, Depends

from api.deps import require, stub
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
    return stub("map")
