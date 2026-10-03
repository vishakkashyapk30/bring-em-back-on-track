"""Capacity allocator (D3): priority = p_break * min(amount_at_risk, CAP) - contact_cost - lambda * p_complaint,
filled greedily (highest priority first) into channel_capacity by time band and into each agent's call slots from
agent_shifts. What does not fit is deferred to the next day and says why. Policy rules were applied before this:
the allocator only ever chooses among actions the gate already allowed."""

from __future__ import annotations


def priority(
    p: float | None, amount: float, cap: float, cost: float, cfg: dict, complaint_p: float | None = None
) -> float:
    a = cfg["allocator"]
    p_eff = cfg["default_p_break"] if p is None else p
    c = a["complaint_rate"] if complaint_p is None else complaint_p
    return round(p_eff * min(amount, cap) - cost - a["lambda_complaint"] * c, 2)


def allocate(
    decisions: list[dict],
    capacity: dict[tuple[str, str], int],
    agent_slots: dict[str, int] | None = None,
    outage: set[str] | None = None,
) -> list[dict]:
    """Mark each decision `scheduled` or `deferred` (with `deferred_reason`). Mutates and returns `decisions`.

    capacity: (channel, time_band) -> units left today. agent_slots: agent id -> outbound call slots left.
    outage: channels that cannot be used today (everything planned on them is deferred, then re-planned by the caller).
    """
    cap = dict(capacity)
    slots = dict(agent_slots or {})
    outage = outage or set()
    for d in sorted((d for d in decisions if d["treatment"] != "no_contact"), key=lambda d: -d["priority"]):
        ch, band = d["channel"], d["window"]
        if ch in outage:
            d["status"], d["deferred_reason"] = "deferred", f"The {ch} channel is down today"
            continue
        # try the planned window first, then the other windows the customer's hours allow
        tries = [(ch, b) for b in [band, *d.get("alt_windows", [])]] + [(ch, "all_day")]
        key = next((k for k in tries if cap.get(k, 0) > 0), None)
        if key is None:
            d["status"], d["deferred_reason"] = "deferred", "No capacity left in this channel and window today"
            continue
        d["window"] = key[1] if key[1] != "all_day" or band == "all_day" else band
        if ch == "call" and d.get("assigned_agent_id") in slots:
            if slots[d["assigned_agent_id"]] <= 0:
                d["status"], d["deferred_reason"] = "deferred", "The assigned agent has no call slots left today"
                continue
            slots[d["assigned_agent_id"]] -= 1
        cap[key] -= 1
        d["status"], d["deferred_reason"] = "scheduled", None
    for d in decisions:
        if d["treatment"] == "no_contact":
            d["status"], d["deferred_reason"] = "no_action", None
    return decisions
