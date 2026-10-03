from __future__ import annotations

from pydantic import BaseModel


class ApproveIn(BaseModel):
    note: str | None = None


class PlaybookApproved(BaseModel):
    ok: bool = True
    audit_id: int
    proposal_id: str
    status: str
    batch_id: str
    batch_status: str
    note: str


class DriftApproved(BaseModel):
    ok: bool = True
    audit_id: int
    fix_id: str
    status: str
    applied: bool = False
    note: str
