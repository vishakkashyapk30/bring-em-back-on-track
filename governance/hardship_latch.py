"""Hardship latch. Anything may raise to 'possible'; only a person confirms or lowers,
and lowering needs a reason. Models/rules can never lower the flag.

`check` is the pure rule (no database); `transition` runs it, then writes the audit row and the event.

* Raise to `possible`: any source (model, rule, LLM, agent, customer form, specialist).
* Confirm (`clear`): a hardship specialist, linking a program.
* Lower (to `possible` or `none`): a hardship specialist, with a non-blank reason.
* Roles that do not service customers (analyst, steward) change nothing.
"""

from __future__ import annotations

from common.db import ops
from common.types import HardshipLevel
from governance import audit

ORDER = {HardshipLevel.none: 0, HardshipLevel.possible: 1, HardshipLevel.clear: 2}
HUMAN_SOURCES = {"agent_coded", "specialist", "customer_form"}
SERVICING_ROLES = {"agent", "hardship_specialist", "team_lead"}


class LatchError(PermissionError):
    pass


def check(current: HardshipLevel, target: HardshipLevel, source: str, role: str, reason: str | None = None,
          program_id: str | None = None) -> None:
    """Raise `LatchError` unless this change is allowed. Pure: reads and writes nothing."""
    current, target = HardshipLevel(current), HardshipLevel(target)
    role = getattr(role, "value", role)
    person = source in HUMAN_SOURCES
    lowering = ORDER[target] < ORDER[current]
    confirming = target == HardshipLevel.clear and current != HardshipLevel.clear
    if person and role not in SERVICING_ROLES:
        raise LatchError("This role does not service customers, so it cannot change a hardship flag")
    if lowering and not person:
        raise LatchError("Only a person can lower a hardship flag")
    if confirming and not person:
        raise LatchError("Only a person can confirm hardship (clear); models and rules can only raise to possible")
    if lowering and role != "hardship_specialist":
        raise LatchError("Only a hardship specialist can lower the flag")
    if lowering and not (reason or "").strip():
        raise LatchError("Lowering a hardship flag needs a reason")
    if confirming and role != "hardship_specialist":
        raise LatchError("Confirming hardship (clear) is a specialist action")  # TBC with policy
    if confirming and not (program_id or "").strip():
        raise LatchError("Confirming hardship (clear) means linking a program")


def transition(golden_id: str, current: HardshipLevel, target: HardshipLevel, source: str,
               user_id: str, role: str, reason: str | None = None, program_id: str | None = None) -> int:
    try:
        check(current, target, source, role, reason, program_id)
    except LatchError as e:  # a refused attempt leaves a trace too
        audit.record(user_id, role, "hardship_flag_refused", "customer", golden_id,
                     {"from": current, "to": target, "source": source, "reason": reason, "program_id": program_id},
                     {"refused": str(e)})
        raise
    audit_id = audit.record(user_id, role, "hardship_flag", "customer", golden_id,
                            {"from": current, "to": target, "source": source, "reason": reason})
    with ops() as con:
        con.execute(
            """INSERT INTO hardship_flag_events (golden_id, from_level, to_level, source, reviewer_id, reason,
               program_id, audit_id) VALUES (?,?,?,?,?,?,?,?)""",
            (golden_id, current, target, source, user_id, reason, program_id, audit_id),
        )
    return audit_id
