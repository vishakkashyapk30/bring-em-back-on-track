"""Hardship latch. Anything may raise to 'possible'; only a person confirms or lowers,
and lowering needs a reason. Models/rules can never lower the flag."""

from __future__ import annotations

from common.db import ops
from common.types import HardshipLevel
from governance import audit

ORDER = {HardshipLevel.none: 0, HardshipLevel.possible: 1, HardshipLevel.clear: 2}
HUMAN_SOURCES = {"agent_coded", "specialist", "customer_form"}


class LatchError(PermissionError):
    pass


def transition(golden_id: str, current: HardshipLevel, target: HardshipLevel, source: str,
               user_id: str, role: str, reason: str | None = None, program_id: str | None = None) -> int:
    lowering = ORDER[target] < ORDER[current]
    if lowering and source not in HUMAN_SOURCES:
        raise LatchError("Only a person can lower a hardship flag")
    if lowering and not reason:
        raise LatchError("Lowering a hardship flag needs a reason")
    if target == HardshipLevel.clear and role != "hardship_specialist" and source != "agent_coded":
        raise LatchError("Confirming hardship (clear) is a specialist action")  # TBC with policy
    if lowering and role != "hardship_specialist":
        raise LatchError("Only a hardship specialist can lower the flag")
    audit_id = audit.record(user_id, role, "hardship_flag", "customer", golden_id,
                            {"from": current, "to": target, "source": source, "reason": reason})
    with ops() as con:
        con.execute(
            """INSERT INTO hardship_flag_events (golden_id, from_level, to_level, source, reviewer_id, reason,
               program_id, audit_id) VALUES (?,?,?,?,?,?,?,?)""",
            (golden_id, current, target, source, user_id, reason, program_id, audit_id),
        )
    return audit_id
