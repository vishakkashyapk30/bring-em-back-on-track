"""Track: each persona follows one subject over time (api/services/track.py, docs/track.md).

Authorisation runs before any data is read: the role decides which kinds of subject it may track, and the row scope
(api/access.py) decides which customers. Reads use the read-only warehouse. The only write here is an analyst's
strategy-test proposal, stored through the playbook store and written to the audit log; every other action in a
tracker calls an existing endpoint, which writes the audit log itself.
"""

from fastapi import APIRouter, Depends, HTTPException

from api.deps import live_data, require
from api.schemas.track import Kinds, Proposed, ProposeIn, SubjectList, TrackView
from api.services import track as svc
from common.types import Role

router = APIRouter(prefix="/track", tags=["track"])
EVERYONE = {Role.agent, Role.hardship_specialist, Role.team_lead, Role.analyst, Role.steward}


def _live() -> None:
    if not live_data():
        raise HTTPException(503, detail={"reason": "Tracking needs the real warehouse, and none is loaded yet."})


@router.get("/kinds")
def kinds(s=Depends(require(EVERYONE))) -> Kinds:
    """What the signed-in person may track, and the guided demo's suggested subject."""
    if not live_data():
        return Kinds(role=str(s.role), kinds=[], suggested=None)
    return svc.kinds(s)


@router.get("/subjects")
def subjects(kind: str, q: str = "", s=Depends(require(EVERYONE))) -> SubjectList:
    """Picker list for one kind, scoped to the person (agent: own customers; specialist: hardship row rule; team lead:
    own team or radar employers with 10+ customers; analyst: cohorts; steward: identities and data products)."""
    svc._check_kind(s, kind)
    _live()
    return svc.subjects(s, kind, q)


@router.get("/{kind}/{subject_id:path}")
def track(kind: str, subject_id: str, s=Depends(require(EVERYONE))) -> TrackView:
    """One subject's history, insights (each with its reason and source) and the actions open to this person."""
    svc._check_kind(s, kind)
    _live()
    return svc.view(s, kind, subject_id)


@router.post("/cohort/{cohort_id}/propose")
def propose(cohort_id: str, body: ProposeIn, s=Depends(require({Role.analyst}))) -> Proposed:
    """Analyst: propose a strategy test on a cohort for a team lead to approve. Audited; contacts nobody."""
    _live()
    return svc.propose_test(s, cohort_id, body.strategy_code, body.note)
