from fastapi import APIRouter, Depends

from api.deps import live_or_fixture, require
from api.schemas.common import WriteResult
from api.schemas.nba import IdentityVerdictIn
from api.services import analytics
from common.db import ops
from common.types import Role
from governance import audit

router = APIRouter(prefix="/steward", tags=["steward"])


@router.get("/identity/queue")
def queue(s=Depends(require({Role.steward}))):
    """Grey-band identity candidates (identity.review_queue), masked for the steward."""
    return live_or_fixture("identity_queue", analytics.identity_queue)


@router.post("/identity/{pair_id}")
def verdict(pair_id: str, body: IdentityVerdictIn, s=Depends(require({Role.steward}))) -> WriteResult:
    """Record the steward's verdict (applied on the next identity run). Audited."""
    audit_id = audit.record(s.user_id, s.role, "identity_review", "identity_pair", pair_id, {"verdict": body.verdict})
    with ops() as con:
        con.execute("""INSERT INTO identity_reviews (pair_id, left_id, right_id, verdict, reviewer_id, ts)
                       VALUES (?, '', '', ?, ?, datetime('now'))
                       ON CONFLICT(pair_id) DO UPDATE SET verdict = excluded.verdict,
                       reviewer_id = excluded.reviewer_id,
                       ts = excluded.ts""", (pair_id, body.verdict, s.user_id))
    return WriteResult(audit_id=audit_id)
