"""Row-level access: which customers, cases and calls a signed-in person may open.

Agents work only the cases assigned to them (assigned_agent_id), team leads the cases of their team. Other roles keep
the access their role already has (hardship specialists work the hardship cases across sites, stewards the identity
queue; analysts see aggregates only and are refused by the role check before reaching here). Applies to reads and
writes alike, in every answer mode. When the app serves sample data (no warehouse) nothing is enforced.
"""

from __future__ import annotations

from fastapi import HTTPException

from api.deps import live_data
from api.schemas.common import Session
from common.types import Role


def _deny(what: str) -> HTTPException:
    return HTTPException(403, detail={"reason": f"This {what} is not assigned to you."})


def _scoped(session: Session) -> tuple[str, str | None] | None:
    if session.role == Role.agent:
        return ("assigned_agent_id", session.user_id)
    if session.role == Role.team_lead:
        return ("assigned_team", session.team_id)
    return None


def _count(session: Session, where: str, param: str) -> int:
    scope = _scoped(session)
    if scope is None:
        return 1
    col, val = scope
    if not val:
        return 0
    from common.db import warehouse

    con = warehouse()
    try:
        con.execute("SET search_path='silver,gold'")
        sql = f"SELECT count(*) FROM collections_cases WHERE {where} AND {col} = ?"
        return con.execute(sql, [param, val]).fetchone()[0]
    finally:
        con.close()


def case(session: Session, case_id: str) -> None:
    if live_data() and _scoped(session) is not None and not _count(session, "case_id = ?", case_id):
        raise _deny("case")


def golden(session: Session, golden_id: str) -> None:
    """A customer is open to you when one of their cases (open or closed) is yours."""
    mine = "case_id IN (SELECT case_id FROM gold.c360_case WHERE golden_id = ?)"
    if live_data() and _scoped(session) is not None and not _count(session, mine, golden_id):
        raise _deny("customer")


def contact(session: Session, contact_id: str) -> None:
    mine = "case_id IN (SELECT case_id FROM contact_history WHERE contact_id = ?)"
    if live_data() and _scoped(session) is not None and not _count(session, mine, contact_id):
        raise _deny("call")
