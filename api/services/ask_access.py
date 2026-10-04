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
    if role == "analyst":
        # Analysts work with aggregates only; a single customer's call is not an aggregate.
        return AskScope(allow_metrics=True, case_allowed=lambda _c: False,
                        case_denied_reason="Refused: analysts see aggregates only, not an individual customer's calls.")
    return AskScope(allow_metrics=False, case_allowed=lambda _c: False)
