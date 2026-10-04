"""Saved watchlist: pin a subject to follow it (audited), list pins with what changed since you last looked."""

from fastapi import APIRouter, Depends

from api.deps import require
from api.schemas.watchlist import Kind, Pin, PinIn, PinResult, WatchList
from api.services import watchlist as svc
from governance.rbac import ALL

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


@router.get("")
def listing(s=Depends(require(ALL))) -> WatchList:
    """Your pins, each with the facts now and what changed since you last looked (read-only)."""
    return svc.listing(s)


@router.get("/pins")
def pins(s=Depends(require(ALL))) -> list[Pin]:
    """Just the pinned (kind, subject_id) pairs, for the watch buttons."""
    return [Pin(**p) for p in svc.pins(s)]


@router.post("")
def pin(body: PinIn, s=Depends(require(ALL))) -> PinResult:
    """Follow a subject. Refused (403) unless you may open it; analysts follow aggregate kinds only. Audited."""
    return svc.pin(s, body.kind, body.subject_id, body.label)


@router.delete("/{kind}/{subject_id:path}")
def unpin(kind: Kind, subject_id: str, s=Depends(require(ALL))) -> PinResult:
    """Stop following a subject. Audited."""
    return svc.unpin(s, kind, subject_id)


@router.post("/{kind}/{subject_id:path}/seen")
def seen(kind: Kind, subject_id: str, s=Depends(require(ALL))) -> dict:
    """Mark as looked at: the facts now become the baseline for the next 'what changed'."""
    return svc.mark_seen(s, kind, subject_id)
