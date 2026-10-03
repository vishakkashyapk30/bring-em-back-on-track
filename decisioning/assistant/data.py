"""Small read-only helpers shared by the assistant tools: the nightly queue (cached by file time), case ownership and
a time-limited cache for tools that are slow to compute."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

import pandas as pd

from decisioning import nba

_lock = threading.Lock()
_queue: dict[str, Any] = {"mtime": None, "df": None}
_ttl: dict[Any, tuple[float, Any]] = {}

QUEUE_COLS = ["case_id", "golden_id", "name", "product", "dpd", "treatment", "channel", "status", "hardship_flag",
              "route_to", "review_mode", "assigned_agent_id", "assigned_team", "priority", "p_break", "risk_band",
              "headline", "program_id", "window", "overdue", "plan_date", "vulnerable"]


def queue_df() -> pd.DataFrame | None:
    """The nightly queue, or None when it has not been built. Re-read only when the file changes."""
    p = nba.queue_path()
    if not p.exists():
        return None
    m = p.stat().st_mtime
    with _lock:
        if _queue["mtime"] != m:
            cols = pd.read_parquet(p).columns
            _queue["df"] = pd.read_parquet(p, columns=[c for c in QUEUE_COLS if c in cols])
            _queue["mtime"] = m
        return _queue["df"]


def case_row(case_id: str) -> dict | None:
    df = queue_df()
    if df is None:
        return None
    r = df[df.case_id == case_id]
    return None if r.empty else r.iloc[0].to_dict()


def case_for_golden(golden_id: str, session=None) -> str | None:
    """The queue case of a golden ID (the one the person may see, when a session is given)."""
    df = queue_df()
    if df is None:
        return None
    r = df[df.golden_id == golden_id]
    if session is not None and not r.empty:
        mine = r[[can_see(session, x) for x in r.to_dict("records")]]
        r = mine
    return None if r.empty else str(r.sort_values("priority", ascending=False).iloc[0].case_id)


def can_see(session, row: dict) -> bool:
    """The same scoping as the queue endpoint: an agent sees own cases, a team lead the team's, a specialist
    any hardship case (the review board and missed-offer list are not limited by site either)."""
    role = getattr(session.role, "value", session.role)
    if role == "agent":
        return row.get("assigned_agent_id") == session.user_id
    if role == "team_lead":
        return row.get("assigned_team") == session.team_id
    if role == "hardship_specialist":
        return row.get("route_to") == "hardship_specialist" or row.get("hardship_flag") not in (None, "none")
    return False


def ttl_cached(key: Any, seconds: float, fn: Callable[[], Any]) -> Any:
    now = time.time()
    hit = _ttl.get(key)
    if hit and now - hit[0] < seconds:
        return hit[1]
    val = fn()
    _ttl[key] = (now, val)
    return val


def clear_caches() -> None:
    _ttl.clear()
    _queue.update(mtime=None, df=None)
