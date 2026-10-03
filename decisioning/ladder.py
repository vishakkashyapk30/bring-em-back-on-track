"""Treatment ladder (rules). Phase 1 NBA = rules informed by risk, not uplift (D2)."""

from decisioning.schemas import Action, GateResult


def choose(case: dict, p_break: float | None, gate_result: GateResult, cfg: dict) -> tuple[Action, list]:
    """Return (action, reason codes). TODO(WS-D).

    Rules: open PTP + low risk -> no_contact; high risk + due within 3 days -> reminder near payday;
    broken PTP + payroll delay -> plan_offer; 31+ DPD + high risk -> agent call;
    hardship or vulnerable -> specialist_referral; otherwise payment_link.
    """
    raise NotImplementedError
