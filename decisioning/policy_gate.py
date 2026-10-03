"""Policy gate: plain rules BEFORE any model. Returns allowed actions plus a
reason code for every exclusion. Never put an LLM here.

Rules: cease/insolvency/deceased -> no contact; third-party rep -> person; open dispute -> pause;
channel needs consent; calls only within permitted_call_start/end_local in time_zone, not Sunday unless
sunday_contact_permitted, not holidays, under contact_cap_7d; internal_do_not_call_flag blocks calls (TBC);
hardship possible/clear or vulnerability -> no pressure treatments + certified agent; stale features
(contract rule 11) -> block. national_dncl_flag and CASL are marketing-only: ignored here by design.
"""

from __future__ import annotations

from decisioning.schemas import GateResult


def gate(case: dict, customer: dict, contacts_7d: int, now_local, feature_age_hours: float) -> GateResult:
    raise NotImplementedError("TODO(WS-D)")
