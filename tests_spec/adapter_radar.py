"""Binding for the S1 radar, S3 drift telemetry and H5 outage shield at unit level (production modules, glue only).

* S1: decisioning/radar.py (rules and arithmetic, small groups hidden, ops_events checked first)
* S3: governance/drift.py (detection plus the drafted fix; the fix is only ever pending an engineer)
* H5: decisioning/outage_shield.py (candidate list plus proposals for a team lead)

`bind(adapter)` puts these operations on an adapter instance, so one hook line in adapter_impl.make_adapter is enough.
"""

from __future__ import annotations

import types
from typing import Any

from tests_spec.adapter import (
    DriftReport,
    OutageVictimReport,
    ProposedAction,
    ProposedFix,
    RadarRow,
)


def _release_notes(docs) -> list[dict[str, Any]]:
    return [dict(d) for d in docs]


class RadarMixin:
    def employer_radar(self, observations, ops_events=()):
        from decisioning import radar

        obs = [radar.Observation(
            golden_id=o.golden_id, employer_key=o.employer_key, industry_naics2=o.industry_naics2,
            week_start=o.week_start, payroll_gap=o.payroll_gap, new_ei_deposit=o.new_ei_deposit,
            payroll_amount_change_pct=o.payroll_amount_change_pct, has_open_case=o.has_open_case,
            exposure_cad=o.exposure_cad) for o in observations]
        rows = radar.compute(obs, ops_events)
        return [RadarRow(employer_key=r["employer_key"], n_customers=r["n_customers"],
                         n_payroll_gap=r["n_payroll_gap"], n_new_ei=r["n_new_ei"], pattern=r["pattern"],
                         explained_by_incident=r["explained_by_incident"], open_cases=r["open_cases"],
                         exposure_cad=r["exposure_cad"], label=r["label"]) for r in rows]

    def detect_schema_drift(self, table, baseline_batch, new_batch):
        from governance import drift

        change = drift.detect(table, baseline_batch, new_batch)
        fix = drift.draft_fix(change)  # drafted only; storing and approving it is the steward's job
        pf = ProposedFix(fix["fix_id"], fix["description"], fix["status"], fix["applied"]) if fix else None
        return DriftReport(table, change["added_columns"], change["removed_columns"], change["row_count_change"],
                           change["null_rate_changes"], change["explanation_sources"], pf)

    def find_outage_victims(self, event, repayments):
        from decisioning import outage_shield

        rows = [{"account_id": r.account_id, "golden_id": r.golden_id, "due_date": r.due_date,
                 "paid_date": r.paid_date, "fees_charged": r.fees_charged, "fees_reversed": r.fees_reversed}
                for r in repayments]
        rep = outage_shield.victims(event, rows)
        props = [ProposedAction(p["proposal_id"], p["kind"], p["subject_id"], "pending_approval", "team_lead")
                 for p in rep["proposals"]]
        return OutageVictimReport(rep["candidates"], rep["our_count"], rep["bank_estimate"],
                                  rep["is_candidate_list"], props)


def bind(adapter):
    """Put the radar, drift and outage operations on this adapter instance."""
    for name in ("employer_radar", "detect_schema_drift", "find_outage_victims"):
        setattr(adapter, name, types.MethodType(getattr(RadarMixin, name), adapter))
    return adapter
