# ruff: noqa: E501
"""Row-level access: which customers, cases and calls a signed-in person may open.

Agents work only the cases assigned to them (assigned_agent_id), team leads the cases of their team. Hardship
specialists open only cases on the hardship board, flagged hardship or vulnerable, or assigned to them or their team
(rule below, docs/reference/row_scope.md). Stewards never open an individual customer's record, calls or notes (identity lineage
is a separate route, `lineage`). Analysts see aggregates only and are refused by the role check before reaching
here. Applies to reads and writes alike, in every answer mode. When the app serves sample data (no warehouse)
nothing is enforced.
"""

from __future__ import annotations

from fastapi import HTTPException

from api.deps import live_data
from api.schemas.common import Session
from common.types import Role

STEWARD_DENIED = ("Stewards see data quality, identity lineage and features, not an individual customer's calls, "
                  "notes or call summaries.")
SPECIALIST_DENIED = ("This case is not on the hardship board, not flagged hardship or vulnerable, and not assigned to "
                     "you or your team.")


def _deny(what: str, session: Session | None = None) -> HTTPException:
    if session is not None and session.role == Role.hardship_specialist:
        return HTTPException(403, detail={"reason": SPECIALIST_DENIED})
    return HTTPException(403, detail={"reason": f"This {what} is not assigned to you."})


# Row scope for hardship specialists (decided from the data model, see docs/reference/row_scope.md). A case is open to a
# hardship specialist when ANY of these holds:
#   1. it is assigned to them (collections_cases.assigned_agent_id) or to their team (assigned_team);
#   2. the case itself is flagged hardship (hardship_flag) or vulnerable (vulnerable_customer_flag);
#   3. the customer is on the hardship board or flagged at customer level (gold.c360_customer.hardship_flag is
#      'possible' or 'clear', or vulnerability_flag), which covers every customer on the review board;
#   4. the latest hardship_flag_events row for the customer in the ops store is not 'none' (flagged since the last
#      nightly build).
# Everything else is refused before any data is read. Protected attributes are never used.
_SPECIALIST_SQL = (
    "(assigned_agent_id = ? OR assigned_team = ? OR hardship_flag OR vulnerable_customer_flag OR case_id IN ("
    "SELECT k.case_id FROM gold.c360_case k JOIN gold.c360_customer c USING (golden_id) "
    "WHERE c.hardship_flag IN ('possible', 'clear') OR c.vulnerability_flag))"
)


def _scoped(session: Session) -> tuple[str, list] | None:
    """(SQL predicate over collections_cases, its parameters), or None when the role has no row scope here."""
    if session.role == Role.agent:
        return ("assigned_agent_id = ?", [session.user_id])
    if session.role == Role.team_lead:
        return ("assigned_team = ?", [session.team_id])
    if session.role == Role.hardship_specialist:
        return (_SPECIALIST_SQL, [session.user_id, session.team_id])
    return None


def _flagged_in_ops(golden_ids: list[str]) -> bool:
    from common.db import ops

    with ops() as con:
        for g in golden_ids:
            r = con.execute("SELECT to_level FROM hardship_flag_events WHERE golden_id = ? ORDER BY event_id DESC "
                            "LIMIT 1", (g,)).fetchone()
            if r and r["to_level"] != "none":
                return True
    return False


def _count(session: Session, where: str, param: str) -> int:
    scope = _scoped(session)
    if scope is None:
        return 1
    pred, params = scope
    if not any(params):
        return 0
    from common.db import warehouse

    con = warehouse()
    try:
        con.execute("SET search_path='silver,gold'")
        sql = f"SELECT count(*) FROM collections_cases WHERE {where} AND {pred}"
        n = con.execute(sql, [param, *params]).fetchone()[0]
        if n or session.role != Role.hardship_specialist:
            return n
        gids = [r[0] for r in con.execute(
            f"SELECT DISTINCT golden_id FROM gold.c360_case WHERE case_id IN "
            f"(SELECT case_id FROM collections_cases WHERE {where})", [param]).fetchall()]
    finally:
        con.close()
    return int(_flagged_in_ops(gids))


def lineage(session: Session, golden_id: str) -> None:
    """Identity lineage (source keys, method, confidence): open to stewards. Others follow the case-row scope."""
    if session.role != Role.steward:
        golden(session, golden_id)


def individual(session: Session) -> None:
    """Stewards get aggregates and identity lineage only: refuse an individual customer's record, calls and notes."""
    if session.role == Role.steward:
        raise HTTPException(403, detail={"reason": STEWARD_DENIED})


def case(session: Session, case_id: str) -> None:
    individual(session)
    if live_data() and _scoped(session) is not None and not _count(session, "case_id = ?", case_id):
        raise _deny("case", session)


def golden(session: Session, golden_id: str) -> None:
    """A customer is open to you when one of their cases (open or closed) is yours."""
    individual(session)
    mine = "case_id IN (SELECT case_id FROM gold.c360_case WHERE golden_id = ?)"
    if live_data() and _scoped(session) is not None and not _count(session, mine, golden_id):
        raise _deny("customer", session)


def contact(session: Session, contact_id: str) -> None:
    individual(session)
    mine = "case_id IN (SELECT case_id FROM contact_history WHERE contact_id = ?)"
    if live_data() and _scoped(session) is not None and not _count(session, mine, contact_id):
        raise _deny("call", session)
