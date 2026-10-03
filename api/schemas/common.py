from __future__ import annotations

from pydantic import BaseModel

from common.types import Role


class Session(BaseModel):
    user_id: str
    role: Role
    team_id: str | None = None
    display_name: str | None = None


class Meta(BaseModel):
    as_of: str | None = None
    freshness_hours: float | None = None
    role: str | None = None
    request_id: str | None = None


class WriteResult(BaseModel):
    ok: bool = True
    audit_id: int
