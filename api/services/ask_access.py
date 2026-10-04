"""Ask authorisation per persona (see common/ask_scope.py). Decided from the session, before any question is run."""

from __future__ import annotations

from common.ask_scope import AskScope


def _case_owner(case_id: str) -> tuple[str | None, str | None] | None:
    from common.db import warehouse

    con = warehouse()
    try:
        con.execute("SET search_path='silver,gold'")
        return con.execute("SELECT assigned_agent_id, assigned_team FROM collections_cases WHERE case_id = ?",
                           [case_id]).fetchone()
    finally:
        con.close()


def scope_for(role: str, user_id: str | None, team_id: str | None) -> AskScope:
    if role == "agent":
        def mine(case_id: str) -> bool:
            row = _case_owner(case_id)
            return bool(row and row[0] == user_id)

        return AskScope(allow_metrics=False, user_id=user_id, role=role, case_allowed=mine,
                        case_denied_reason="Refused: you can only open call summaries for your own cases.")
    if role == "team_lead":
        def team(case_id: str) -> bool:
            row = _case_owner(case_id)
            return bool(row and team_id and row[1] == team_id)

        return AskScope(allow_metrics=True, user_id=user_id, role=role, case_allowed=team,
                        case_denied_reason="Refused: you can only open call summaries for cases on your team.")
    if role == "hardship_specialist":
        # Same row rule as the API (api/access.py, docs/row_scope.md): board, flagged hardship or vulnerable, or
        # assigned to you or your team. Decided here, before the call is read, in rules and language-model mode alike.
        def specialist(case_id: str) -> bool:
            from api import access
            from api.schemas.common import Session

            sess = Session(user_id=user_id or "", role="hardship_specialist", team_id=team_id)
            return bool(access._count(sess, "case_id = ?", case_id))

        return AskScope(allow_metrics=False, user_id=user_id, role=role, case_allowed=specialist,
                        case_denied_reason="Refused: that case is not on the hardship board, not flagged hardship or "
                                           "vulnerable, and not assigned to you or your team.")
    if role == "steward":
        # Stewards see data quality, identity and features: never an individual customer's calls, notes or summaries.
        return AskScope(allow_metrics=False, user_id=user_id, role=role, case_allowed=lambda _c: False,
                        case_denied_reason="Refused: stewards see data quality, identity lineage and features, not an "
                                           "individual customer's calls, notes or call summaries.")
    if role == "analyst":
        # Analysts work with aggregates only; a single customer's call is not an aggregate.
        return AskScope(allow_metrics=True, role=role, case_allowed=lambda _c: False,
                        case_denied_reason="Refused: analysts see aggregates only, not an individual customer's calls.")
    return AskScope(allow_metrics=False, role=role, case_allowed=lambda _c: False)
