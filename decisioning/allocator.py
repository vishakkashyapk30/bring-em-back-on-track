"""Capacity allocator (D3): priority = p_break * min(amount_at_risk, CAP) - contact_cost - lambda * p_complaint,
filled greedily into channel_capacity x time_band and agent_shifts; overflow moves to next band/day."""


def allocate(proposals: list, capacity, shifts, cfg: dict) -> list:
    raise NotImplementedError("TODO(WS-D)")
