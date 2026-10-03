"""S6: rerun the allocator with a channel down or agents absent; diff which actions move."""

from __future__ import annotations

import copy
import hashlib

import pandas as pd

from decisioning import nba

RERUN_COLS = ["case_id", "treatment", "channel", "window", "priority", "alt_windows", "assigned_agent_id", "risk_band"]


def rerun(
    rows: list[dict],
    capacity: dict,
    slots: dict[str, int],
    *,
    channels_down: set[str] | None = None,
    slots_after: dict[str, int] | None = None,
) -> tuple[list[dict], list[dict]]:
    """Allocate `rows` twice: as planned, and again with channels down and/or fewer agent slots. Pure: the inputs are
    never changed, so the real plan stays as it was."""
    from decisioning import allocator

    before = allocator.allocate(copy.deepcopy(rows), capacity, slots)
    after = allocator.allocate(
        copy.deepcopy(rows),
        capacity,
        slots_after if slots_after is not None else dict(slots),
        outage=set(channels_down) if channels_down else None,
    )
    return before, after


def run(remove: dict) -> dict:
    df = pd.read_parquet(nba.queue_path())
    plan_date = df.plan_date.iloc[0]
    capacity, _cost, slots = nba._capacity(plan_date)
    rows = df[df.treatment != "no_contact"][RERUN_COLS].to_dict("records")
    for r in rows:
        r["alt_windows"] = list(r["alt_windows"]) if r["alt_windows"] is not None else []

    channel, pct = remove.get("channel"), remove.get("agents_pct")
    slots2 = dict(slots)
    if pct:
        gone = {a for a in slots if int(hashlib.sha1(a.encode()).hexdigest(), 16) % 1000 < pct * 1000}
        for a in gone:
            slots2[a] = 0
    before, after = rerun(rows, capacity, slots, channels_down={channel} if channel else None, slots_after=slots2)

    was = {r["case_id"]: r for r in before}
    moved = [r for r in after if r["status"] == "deferred" and was[r["case_id"]]["status"] == "scheduled"]
    high = [r for r in moved if r["risk_band"] in ("high", "very_high")]
    by_t: dict[str, int] = {}
    for r in moved:
        by_t[r["treatment"]] = by_t.get(r["treatment"], 0) + 1
    return {
        "removed": {"channel": channel, "agents_pct": pct},
        "scheduled_before": sum(r["status"] == "scheduled" for r in before),
        "scheduled_after": sum(r["status"] == "scheduled" for r in after),
        "moved": len(moved),
        "dropped": len(high),
        "by_treatment": [{"treatment": t, "moved": n} for t, n in sorted(by_t.items(), key=lambda x: -x[1])],
        "note": "'moved' means pushed to the next day; 'dropped' counts the high and very high risk cases among them.",
    }
