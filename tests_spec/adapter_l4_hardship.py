"""Layer 4 binding, hardship part: latch, eligibility, plan simulator, review board, missed offers.

Mixed into `adapter_impl.Layer123Adapter`. Rules followed:
* Each operation calls the real module (`governance.hardship_latch`, `decisioning.eligibility`,
  `decisioning.simulator`, `api.services.hardship`); the glue only converts the suite's dataclasses to our shapes.
* Writes (hardship events, audit rows) go through the real code paths into a private temporary ops.db, so the
  adapter never touches `data/ops.db`. `OPS_DB_PATH` is pointed at it only for the duration of each call.
* The warehouse is not needed: the spec passes explicit loan terms, affordability and program rows.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from tests_spec.adapter import (
    Actor,
    AuditRecord,
    CardTerms,
    EligibilityInput,
    EligibilityResult,
    EligibilityRuleResult,
    HardshipFlagEvent,
    HardshipProgram,
    HardshipState,
    HardshipTransitionResult,
    MissedOfferReport,
    PlanRequest,
    PlanScenario,
    ReviewBoardRow,
)

NON_PERSON_SOURCE = {"model": "model", "rule": "model", "llm": "llm_flag"}


def _program_row(p: HardshipProgram) -> dict[str, Any]:
    """A `hardship_programs` row in the shape decisioning.eligibility / simulator read."""
    return {
        "program_id": p.program_id,
        "program_name": p.program_id,
        "product_types": list(p.product_types),
        "min_hardship_level": p.min_hardship_level,
        "max_dpd": p.max_dpd,
        "min_months_on_book": p.min_months_on_book,
        "max_uses_12m": p.max_uses_12m,
        "excludes_insolvency": p.excludes_insolvency,
        "excludes_broken_plan_90d": p.excludes_broken_plan_90d,
        "requires_income_evidence": p.requires_income_evidence,
        "payment_reduction_pct": p.payment_reduction_pct,
        "duration_months": p.duration_months,
        "term_extension_max_months": p.term_extension_max_months,
        "rate_override": p.rate_override,
        "fees_waived_flag": p.fees_waived_flag,
        "approver_level": p.approver_level,
    }


def _eligibility_result(res: dict) -> EligibilityResult:
    return EligibilityResult(
        program_id=res["program_id"],
        eligible=res["eligible"],
        rule_results=[EligibilityRuleResult(r["rule"], r["passed"], r["detail"]) for r in res["rules"]],
        decided_by=res["decided_by"],
        payment_reduction_pct=res["payment_reduction_pct"],
        duration_months=res["duration_months"],
        requires_income_evidence=res["requires_income_evidence"],
    )


class HardshipMixin:
    # ------------------------------------------------------------------ private ops.db
    _hd_dir: Path | None = None

    def reset_hardship(self) -> None:
        """Forget every hardship event and audit row written by this adapter (called from reset())."""
        if self._hd_dir is not None:
            shutil.rmtree(self._hd_dir, ignore_errors=True)
        self._hd_dir = None

    @contextmanager
    def _ops_scope(self):
        from common.config import get_settings

        if self._hd_dir is None:
            self._hd_dir = Path(tempfile.mkdtemp(prefix="spec_hardship_"))
        old = os.environ.get("OPS_DB_PATH")
        os.environ["OPS_DB_PATH"] = str(self._hd_dir / "ops.db")
        get_settings.cache_clear()
        try:
            yield
        finally:
            if old is None:
                os.environ.pop("OPS_DB_PATH", None)
            else:
                os.environ["OPS_DB_PATH"] = old
            get_settings.cache_clear()

    # ------------------------------------------------------------------ latch
    def hardship_transition(
        self,
        current: HardshipState,
        to: str,
        actor: Actor,
        reason: str | None = None,
        program_id: str | None = None,
        source: str | None = None,
    ) -> HardshipTransitionResult:
        # governance/hardship_latch.transition: the rule (check) then the audit row and hardship_flag_events row.
        from common.types import HardshipLevel
        from governance import hardship_latch as latch

        if actor.kind == "person":
            role = actor.role or "agent"
            if source not in latch.HUMAN_SOURCES:  # a person's source is a person's, whatever the caller labels it
                source = "specialist" if role == "hardship_specialist" else "agent_coded"
        else:
            role = "system"
            if source is None or source in latch.HUMAN_SOURCES:
                source = NON_PERSON_SOURCE[actor.kind]
        with self._ops_scope():
            try:
                latch.transition(
                    current.golden_id, HardshipLevel(current.level), HardshipLevel(to), source, actor.actor_id, role,
                    reason, program_id,
                )
            except latch.LatchError as e:
                return HardshipTransitionResult(False, current.level, None, str(e))
        event = HardshipFlagEvent(
            golden_id=current.golden_id, from_level=current.level, to_level=to, actor_id=actor.actor_id,
            actor_kind=actor.kind, source=source, reason=reason, at=dt.datetime.now(dt.UTC), program_id=program_id,
        )
        return HardshipTransitionResult(True, to, event)

    def get_hardship_state(self, golden_id: str) -> HardshipState:
        # api/services/hardship.current_level: last event in hardship_flag_events, else the c360 flag, else none.
        from api.services import hardship as svc
        from common.db import ops

        with self._ops_scope():
            with ops() as con:
                r = con.execute(
                    "SELECT to_level, program_id FROM hardship_flag_events WHERE golden_id = ? "
                    "ORDER BY event_id DESC LIMIT 1", (golden_id,),
                ).fetchone()
            if r:
                return HardshipState(golden_id, r["to_level"], r["program_id"])
            try:
                return HardshipState(golden_id, svc.current_level(golden_id))
            except Exception:  # noqa: BLE001, no warehouse in this environment: nothing recorded means none
                return HardshipState(golden_id, "none")

    def audit_log(self, event_type: str | None = None, subject_id: str | None = None) -> list[AuditRecord]:
        # governance/audit.query over this adapter's private ops.db.
        from governance import audit

        filters = {k: v for k, v in (("event_type", event_type), ("entity_id", subject_id)) if v is not None}
        with self._ops_scope():
            rows = audit.query(limit=10_000, **filters)
        out = []
        for r in reversed(rows):
            payload = json.loads(r["payload_json"] or "{}")
            inputs = payload.get("inputs")
            details = dict(inputs) if isinstance(inputs, dict) else {"inputs": inputs}
            details["outputs"] = payload.get("outputs")
            out.append(AuditRecord(
                audit_id=str(r["audit_id"]), event_type=r["event_type"], actor_id=r["user_id"], actor_role=r["role"],
                subject_id=r["entity_id"], at=dt.datetime.fromisoformat(r["ts"].replace("Z", "+00:00")),
                details=details, reason=details.get("reason"),
            ))
        return out

    # ------------------------------------------------------------------ eligibility
    def check_eligibility(self, applicant: EligibilityInput, program: HardshipProgram) -> EligibilityResult:
        # decisioning/eligibility.evaluate. Free text and protected attributes are never passed on.
        from decisioning import eligibility

        res = eligibility.evaluate(
            _program_row(program),
            {
                "product": applicant.product,
                "dpd": applicant.days_past_due,
                "months_on_book": applicant.months_on_book,
                "hardship_level": applicant.hardship_flag,
                "insolvency": applicant.insolvency,
                "uses_12m": applicant.program_uses_12m,
                "broken_plan_90d": applicant.broken_plan_last_90d,
            },
        )
        return _eligibility_result(res)

    # ------------------------------------------------------------------ plan simulator
    def simulate_plan(self, request: PlanRequest) -> PlanScenario:
        # decisioning/simulator: project (arithmetic), monthly_surplus, rejected_levers, limits_exceeded.
        from common.hashing import stable_hash
        from decisioning import simulator as sim
        from governance import audit

        acct, lv, prog = request.account, request.levers, _program_row(request.program)
        card = isinstance(acct, CardTerms)
        if card:
            balance, apr, payment_now, fees = acct.current_balance, acct.purchase_apr, acct.minimum_payment_due, 0.0
        else:  # fees carry no interest: they are paid on top and can be waived
            balance, apr = acct.principal_balance + acct.accrued_interest, acct.interest_rate
            payment_now, fees = acct.scheduled_payment_amount, acct.fees_outstanding
        asked = {
            "term_extension_months": lv.term_extension_months,
            "payment_reduction_pct": lv.payment_reduction_pct,
            "rate_override": lv.rate_override,
            "payment_holiday_months": lv.payment_holiday_months,
            "fee_waiver": lv.fee_waiver,
        }
        rejected = sim.rejected_levers("card" if card else "loan", asked)
        used = {k: (None if v is None or k in rejected else v) for k, v in asked.items()}
        ext, hol = int(used["term_extension_months"] or 0), int(used["payment_holiday_months"] or 0)
        red, rate, waive = float(used["payment_reduction_pct"] or 0.0), used["rate_override"], bool(used["fee_waiver"])

        p = sim.project(balance, apr, payment_now, reduction=red, extension=ext, rate=rate, holiday=hol,
                        fees=fees, waive_fees=waive)
        a = request.affordability
        surplus = sim.monthly_surplus(a.payroll_avg_amount_3m, a.essential_spend_amount_mtd,
                                      a.other_lender_payment_amount_mtd, a.as_of)
        base, scen = p["base"], p["scenario"]
        clears, clears_base = scen["months"] is not None, base["months"] is not None
        beyond = sim.limits_exceeded(prog, red, ext, rate, hol, waive)
        scenario_id = "SCN-" + stable_hash({"g": request.golden_id, "a": acct.account_id, "p": prog["program_id"],
                                            "asked": asked})[:12]
        out = PlanScenario(
            scenario_id=scenario_id,
            new_payment=p["new_payment"],
            baseline_payment=payment_now,
            monthly_surplus=surplus,
            payment_to_surplus_ratio=p["new_payment"] / surplus if surplus and surplus > 0 else None,
            months_to_clear=float(scen["months"]) if clears else None,
            baseline_months_to_clear=float(base["months"]) if clears_base else None,
            total_interest=scen["interest"] if clears else None,
            baseline_total_interest=base["interest"] if clears_base else None,
            total_customer_paid=p["paid_plan"] if clears else None,
            bank_value_plan=p["pv_plan"],
            status_quo_value=request.total_exposure - request.expected_loss_est,
            plan_hold_rate=None,  # no similar plans in the request; the label still applies
            plan_hold_label="observed, not causal",
            within_program_rules=not beyond,
            approver_level_required=prog["approver_level"],
            rejected_levers=rejected,
            assumptions=dict(sim.ASSUMPTIONS),
        )
        by = request.requested_by
        with self._ops_scope():
            audit.record(
                by.actor_id, str(by.role or "system"), "simulator_run", "scenario", scenario_id,
                {"scenario_id": scenario_id, "golden_id": request.golden_id, "program_id": prog["program_id"],
                 "levers": asked, "rejected_levers": rejected},
                {"new_payment": out.new_payment, "months_to_clear": out.months_to_clear,
                 "within_program_rules": out.within_program_rules},
            )
        return out

    # ------------------------------------------------------------------ review board, missed offers
    def review_board(self, customers, as_of: dt.date) -> list[ReviewBoardRow]:
        # api/services/hardship.review_board_rows (uses vulnerability_flag only, never vulnerability_type).
        from api.services import hardship as svc

        return [ReviewBoardRow(r["golden_id"], r["vulnerability_review_date"], r["hardship_flag"], r["hardship_source"])
                for r in svc.review_board_rows(customers, as_of)]

    def missed_offers(self, cases, offers) -> MissedOfferReport:
        # api/services/hardship.missed_offer_report
        from api.services import hardship as svc

        rep = svc.missed_offer_report(cases, offers)
        return MissedOfferReport(rep["missed"], rep["overridden_offers"], rep["decline_reasons"])
