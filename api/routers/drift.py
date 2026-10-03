"""S3 schema-drift telemetry. The fix is drafted, never applied by the app; only the data steward approves it."""

from fastapi import APIRouter, Depends, HTTPException

from api.deps import live_data, require
from api.schemas.playbooks import ApproveIn, DriftApproved
from common.types import Role
from governance import drift

router = APIRouter(tags=["drift"])


@router.get("/drift")
def telemetry(s=Depends(require({Role.steward, Role.analyst}))):
    """Detected changes (from ops_events releases and feed issues on the real warehouse) and the drafted fixes."""
    scans = []
    if live_data():
        for c in drift.scan_warehouse():
            fix = drift.record(c)
            scans.append({**{k: v for k, v in c.items() if k != "null_rate_changes"},
                          "null_rate_changes": dict(sorted(c["null_rate_changes"].items(),
                                                           key=lambda kv: -abs(kv[1]))[:10]),
                          "fix_id": fix["fix_id"] if fix else None})
    items = drift.fixes()
    return {"scans": scans, "fixes": items, "pending": sum(f["status"] == drift.PENDING for f in items),
            "empty_state": None if items else "No schema change found. Nothing needs an engineer."}


@router.post("/drift/{fix_id}/approve")
def approve(fix_id: str, body: ApproveIn | None = None, s=Depends(require({Role.steward}))) -> DriftApproved:
    try:
        res = drift.approve_fix(fix_id, s.user_id, s.role, body.note if body else None)
    except KeyError as e:
        raise HTTPException(404, "No fix with that ID") from e
    except ValueError as e:
        raise HTTPException(409, detail={"reason": str(e)}) from e
    return DriftApproved(**{k: res[k] for k in DriftApproved.model_fields if k in res})
