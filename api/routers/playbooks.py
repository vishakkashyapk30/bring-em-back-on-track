"""S1 employer radar, H5 outage shield and the team-lead playbook proposals. Nothing here contacts a customer."""

from fastapi import APIRouter, Depends, HTTPException

from api.deps import live_data, require
from api.schemas.playbooks import ApproveIn, PlaybookApproved
from common.types import Role
from decisioning import playbooks, radar

router = APIRouter(tags=["playbooks"])


@router.get("/radar")
def employer_radar(week: str | None = None, s=Depends(require({Role.team_lead, Role.analyst}))):
    """Weekly employer radar from the real warehouse (employers under 10 customers hidden). Says 'no cluster' when
    there is none. A radar, not a layoff detector."""
    if not live_data():
        return radar.empty("No warehouse is loaded, so there is nothing to show yet.")
    return radar.employer_week(week)


@router.get("/playbooks")
def proposals(status: str | None = None, s=Depends(require({Role.team_lead}))):
    """Playbook proposals (employer radar, outage shield, regional). They wait for a team lead."""
    items = playbooks.listing(status)
    return {"items": items, "pending": sum(i["status"] == playbooks.PENDING for i in items),
            "empty_state": None if items else "No proposals right now. The radar and the outage shield found nothing "
                                              "that needs a team lead."}


@router.post("/playbooks/{proposal_id}/approve")
def approve(proposal_id: str, body: ApproveIn | None = None, s=Depends(require({Role.team_lead}))) -> PlaybookApproved:
    """Approve one proposal: audited, creates a batch for the usual sample check, contacts nobody."""
    try:
        res = playbooks.approve(proposal_id, s.user_id, s.role, s.team_id, body.note if body else None)
    except KeyError as e:
        raise HTTPException(404, "No proposal with that ID") from e
    except ValueError as e:
        raise HTTPException(409, detail={"reason": str(e)}) from e
    return PlaybookApproved(**{k: res[k] for k in PlaybookApproved.model_fields if k in res})
