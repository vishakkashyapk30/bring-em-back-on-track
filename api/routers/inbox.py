"""'Waiting for you' inbox (read-only). Approvals stay on the existing screens; each item links there."""

from fastapi import APIRouter, Depends

from api.deps import require
from api.schemas.inbox import InboxCounts, InboxResponse
from api.services import inbox as svc
from governance.rbac import ALL

router = APIRouter(tags=["inbox"])


@router.get("/inbox")
def inbox(s=Depends(require(ALL))) -> InboxResponse:
    """Every pending human review for the signed-in person, grouped by type, in their row scope."""
    return svc.build(s)


@router.get("/inbox/counts")
def counts(s=Depends(require(ALL))) -> InboxCounts:
    """Totals for the nav badge (cached for a few seconds per person)."""
    return svc.counts(s)
