"""Binding of the specification suite (tests_spec/) to Layer 4, next best action.

Mixed into the adapter in `adapter_impl.py` (`NbaMixin` comes first in the bases so these methods replace the
`SpecAdapterBase` stubs).

Rules followed here, as in `adapter_impl.py`:
* Each bound operation calls the real module named in its comment. Glue only converts the suite's dataclasses to
  and from our own shapes (decisioning.schemas pydantic models and plain dicts). No test input is special-cased.
* Protected attributes are never read: `CustomerContact.protected`, `national_dncl_flag` and `casl_consent` are
  dropped at the conversion boundary, and only the model features named in `FEATURE_MAP` reach the score.
* Where the real system has no equivalent for in-memory inputs, the adapter says which production rule it mirrors.
* Not bound on purpose: `propose_next_best_action_for_case` (needs the synthetic Ryan tables loaded through the
  dbt pipeline, which `adapter_impl.NOT_BUILT_PIPELINE` explains).
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import random
from collections.abc import Mapping, Sequence
from functools import lru_cache
from typing import Any
from zoneinfo import ZoneInfo

from tests_spec import spec_constants as C
from tests_spec.adapter import (
    Action,
    ApprovalBatch,
    ChannelCapacity,
    DailyPlan,
    Explanation,
    GateResult,
    ModelEval,
    NbaDecision,
    OpsEvent,
    PayrollInfo,
    PromiseCheck,
    PromiseDraft,
    PromiseOutcome,
    RuleFired,
    StressResult,
    StressScenario,
    UpliftGate,
)

# The spec's time windows <-> our channel_capacity time bands (common.types.TimeBand).
WINDOW_TO_BAND = {"morning": "08-12", "afternoon": "12-17", "evening": "17-21", "any": "all_day"}
BAND_TO_WINDOW = {v: k for k, v in WINDOW_TO_BAND.items()}

# Spec feature names (V1 section 5 vocabulary) -> the columns of the promise-break model (models/ptp_break).
# A model column given under its own name is passed through. Anything else is ignored, so a protected attribute
# can never reach the score.
FEATURE_MAP = {
    "dpd_max_current": "dpd_at_creation",
    "ptp_broken_count_90d": "prior_broken_ptp_count",
    "stated_delay_reason": "last_stated_delay_reason",
}

# The agent pool the allocator sees: the spec gives one number of call slots for the day, not named agents.
POOL = "POOL"
# Business day for operations that take no time argument (apply_treatment_ladder, check_promise): the suite's
# declared reference Tuesday, the same day `factories.AS_OF` names.
DEFAULT_BUSINESS_DATE = C.REFERENCE_WEEKDAY


@lru_cache(maxsize=1)
def _model():
    """The offline promise-break model: LightGBM booster plus isotonic calibrator (models/ptp_break/train.py).
    Without a bank v2.1 score the production fallback applies: our calibrated model alone (score.py)."""
    import json
    import pickle

    import lightgbm as lgb

    from models.ptp_break.train import ART

    meta = json.loads((ART / "meta.json").read_text())
    booster = lgb.Booster(model_file=str(ART / "ptp_break.txt"))
    with open(ART / "calibrator.pkl", "rb") as fh:
        cal = pickle.load(fh)  # noqa: S301 - our own artefact
    return meta, booster, cal


def _frame(features: Mapping[str, Any]):
    import pandas as pd

    meta, _, _ = _model()
    mapped = {FEATURE_MAP.get(k, k): v for k, v in features.items()}
    row: dict[str, Any] = {}
    for f in meta["features"]:
        v = mapped.get(f)
        if f in meta["categorical"]:
            row[f] = pd.Categorical([None if v is None else str(v)], categories=meta["categories"][f])
        else:
            row[f] = [float("nan") if v is None else float(v)]
    return pd.DataFrame(row), {f: mapped.get(f) for f in meta["features"]}


def _score(features: Mapping[str, Any]) -> tuple[float, list[dict]]:
    """(calibrated probability, plain-English reasons that raise the risk) for one feature vector."""
    from models.ptp_break.explain import reason_codes

    meta, booster, cal = _model()
    df, values = _frame(features)
    raw = booster.predict(df[meta["features"]])
    p = float(cal.predict(raw)[0])
    contrib = booster.predict(df[meta["features"]], pred_contrib=True)[0][:-1]
    # only features that were actually given can be a reason: a missing value is not evidence of anything
    given = {f: c for f, c in zip(meta["features"], contrib, strict=True) if values[f] is not None}
    return min(1.0, max(0.0, p)), reason_codes(values, given)


def _row(case, p_break: float | None = None, reasons: list[dict] | None = None) -> dict:
    """A CaseSnapshot as the `decisioning.context.load_cases` row the production code expects."""
    from decisioning import ladder
    from decisioning.nba import CFG

    c = case.customer
    pr, lb = case.open_promise, case.last_broken_promise
    consent = c.consent or {}
    return {
        "case_id": case.case_id,
        "golden_id": c.golden_id,
        "time_zone": c.time_zone,
        "province_code": c.province_code,
        "consent_call": consent.get("call"),
        "consent_sms": consent.get("sms"),
        "consent_email": consent.get("email"),
        "consent_push": consent.get("push"),
        "permitted_call_start_local": c.permitted_call_start_local,
        "permitted_call_end_local": c.permitted_call_end_local,
        "sunday_contact_permitted": c.sunday_contact_permitted,
        "contact_block": c.contact_block,
        "third_party_rep_flag": c.third_party_rep_flag,
        "dispute_open_flag": c.dispute_open_flag,
        "hardship_flag": c.hardship_flag,
        "vulnerability_flag": c.vulnerability_flag,
        "contacts_last_7d": c.contacts_last_7d,
        "contact_cap_7d": c.contact_cap_7d,
        "current_dpd": case.days_past_due,
        "total_overdue": case.amount_at_risk_cad,
        "payroll_delay_days": case.payroll_delay_days,
        "ptp_id": pr.ptp_id if pr else None,
        "ptp_due_date": pr.due_date if pr else None,
        "ptp_amount": pr.amount if pr else None,
        # a promise's "broken on" day is its due date (the suite gives no separate status timestamp)
        "last_broken_ts": lb.due_date if lb else None,
        "last_broken_ptp": lb.ptp_id if lb else None,
        "p_break": p_break,
        "risk_band": ladder.risk_band(p_break, CFG) if p_break is not None else None,
        "risk_model": "our model (no bank v2.1 score)" if p_break is not None else None,
        "reasons": reasons or [],
    }


def _to_spec_action(a) -> Action:
    t = a.treatment.value if hasattr(a.treatment, "value") else a.treatment
    ch = a.channel.value if hasattr(a.channel, "value") else a.channel
    w = a.window.value if hasattr(a.window, "value") else a.window
    return Action(
        treatment=t, channel=ch, window=BAND_TO_WINDOW.get(w), scheduled_at=a.scheduled_at, program_id=a.program_id
    )


def _to_our_action(a: Action):
    from decisioning.schemas import Action as OurAction

    return OurAction(
        treatment=a.treatment,
        channel=a.channel,
        window=WINDOW_TO_BAND.get(a.window) if a.window else None,
        program_id=a.program_id,
        scheduled_at=a.scheduled_at,
    )


def _plan_date(at: dt.datetime, tz: str) -> dt.date:
    return at.astimezone(ZoneInfo(tz)).date() if at.tzinfo else at.date()


class NbaMixin:
    """Layer 4 NBA operations. Put it BEFORE SpecAdapterBase in the bases."""

    business_date: dt.date = DEFAULT_BUSINESS_DATE

    # ---------------- policy gate ----------------
    def policy_gate(self, customer, candidates: Sequence[Action], at: dt.datetime) -> GateResult:
        # decisioning/policy_gate.py gate(); customer fields via customer_from_row (the same path as the nightly queue)
        from decisioning import policy_gate as pg

        row = _row(dataclasses.replace(_blank_case(), customer=customer))
        cust = pg.customer_from_row(row)
        res = pg.gate(cust, [_to_our_action(a) for a in candidates], at)
        by_key = {(a.treatment, a.channel): a for a in candidates}
        return GateResult(
            disposition=res.disposition,  # type: ignore[arg-type]
            permitted=[
                by_key.get((a.treatment.value, a.channel.value if a.channel else None), _to_spec_action(a))
                for a in res.allowed
            ],
            blocked=[
                (
                    by_key.get(
                        (b.treatment.value, b.channel.value if b.channel else None),
                        Action(b.treatment.value, b.channel.value if b.channel else None),
                    ),
                    b.code,
                )
                for b in res.blocked
            ],
            rules_fired=[RuleFired(code=r.code, message=r.text) for r in res.rules_fired],
            route_to=res.route_to,
            pressure_removed=res.pressure_removed,
        )

    # ---------------- ladder ----------------
    def apply_treatment_ladder(self, case, break_probability: float) -> Action:
        # decisioning/nba.py decide(): candidates -> gate -> ladder.choose (policy gate first, then the ladder)
        from decisioning import nba

        d = nba.decide(_row(case, break_probability), plan_date=self.business_date)
        return _to_spec_action(d["action"])

    # ---------------- risk score ----------------
    def score_break_risk(self, features: Mapping[str, Any]) -> float:
        # models/ptp_break artefacts (monotone LightGBM + isotonic calibrator), offline, no bank v2.1 score
        return _score(features)[0]

    def choose_break_model(self, challenger: ModelEval, incumbent: ModelEval) -> str:
        # models/ptp_break/train.py decision rule: replace the bank's model only if ours has a higher AUC on the SAME
        # later set of promises. Anything else keeps the incumbent.
        if challenger.evaluated_on != incumbent.evaluated_on:
            return incumbent.model_id
        return challenger.model_id if challenger.auc > incumbent.auc else incumbent.model_id

    def uplift_readiness(self, overlap_share: float, cases_per_action: Mapping[str, int]) -> UpliftGate:
        # decisioning/nba.py uplift_gate()
        from decisioning import nba

        ok, why = nba.uplift_gate(overlap_share, dict(cases_per_action))
        return UpliftGate(enabled=ok, reason=why)

    # ---------------- NBA ----------------
    def propose_next_best_action(self, case, at: dt.datetime) -> NbaDecision:
        # decisioning/nba.py decide() + explain.explain(), one code path with the nightly queue and the case page
        from decisioning import explain, nba
        from decisioning.allocator import priority

        c = case.customer
        plan_date = _plan_date(at, c.time_zone)
        p, reasons = None, []
        if case.open_promise is not None:  # the break model scores promises: no promise, no score
            p, reasons = _score(case.features)
        row = _row(case, p, reasons)
        if p is not None:
            from models.ptp_break.score import band

            row["risk_band"] = band(p)
        d = nba.decide(row, plan_date=plan_date)
        act, g = d["action"], d["gate"]
        alts = nba.alternatives(d, row)
        ex = explain.explain(act, g, d["reasons"], row, d["customer"], p, alts, plan_date)
        contacting = act.treatment.value != "no_contact"
        # decisioning/nba.py audit_proposal(): every score and proposal is audited (V1 section 10). Written to the
        # adapter's private ops.db when the hardship binding provides one, never to the real audit log.
        scope = getattr(self, "_ops_scope", None)
        if scope is not None:
            with scope():
                nba.audit_proposal(
                    case.case_id,
                    act.treatment.value,
                    act.channel.value if act.channel else None,
                    p,
                    [r.code for r in ex.rules_applied],
                    "nba-engine",
                    "system",
                )
        # Expected value = break chance x amount at risk - contact cost (V1 section 6 step 3). One case has no book to
        # take a 75th-percentile amount cap from, so the amount is not capped here.
        ev = None
        if contacting:
            ev = priority(p, case.amount_at_risk_cad, case.amount_at_risk_cad, case.contact_cost_cad, nba.CFG)
        risk_reasons = [d_.text for d_ in explain.drivers(row, p)]
        rules = [r.text for r in ex.rules_applied]
        changes = [r.text for r in ex.what_changed]
        text = ". ".join(
            [ex.recommendation]
            + ([f"Rules applied: {'; '.join(rules)}"] if rules else [])
            + ([f"Main reasons for the risk: {'; '.join(risk_reasons)}"] if risk_reasons else [])
            + ([f"What changed: {'; '.join(changes)}"] if changes else [])
        )
        return NbaDecision(
            decision_id=f"DEC-{case.case_id}-{plan_date.isoformat()}",
            case_id=case.case_id,
            action=_to_spec_action(act),
            break_probability=p,
            expected_value=ev,
            explanation=Explanation(
                rules_applied=rules,
                risk_reasons=risk_reasons,
                changes=changes,
                text=text,
                generated_by=ex.generated_by,
            ),
            review_mode=nba._review_mode(row, act, g),  # type: ignore[arg-type]
            route_to=g.route_to,
            model_version=row["risk_model"],
            alternatives=[_to_spec_action(_alt(a)) for a in alts if a["allowed"]],
        )

    def propose_next_best_action_for_case(self, case_id: str, at: dt.datetime) -> NbaDecision:
        raise NotImplementedError(
            "needs the synthetic Ryan Mitchell tables loaded through the dbt pipeline (load_sources/run_pipeline are "
            "not bound, see adapter_impl.NOT_BUILT_PIPELINE); the live-warehouse equivalent is decisioning.nba.propose"
        )

    # ---------------- daily plan and stress test ----------------
    @staticmethod
    def _plan_rows(decisions: Sequence[NbaDecision]) -> list[dict]:
        return [
            {
                "decision_id": d.decision_id,
                "treatment": d.action.treatment,
                "channel": d.action.channel,
                "window": WINDOW_TO_BAND.get(d.action.window or "any", "all_day"),
                "priority": d.expected_value or 0.0,
                "alt_windows": [],
                "assigned_agent_id": POOL,
            }
            for d in decisions
        ]

    @staticmethod
    def _capacity_maps(capacity: ChannelCapacity) -> tuple[dict, dict]:
        # the spec gives units per channel for the day: the allocator's "any time" band takes them
        return {(ch, "all_day"): n for ch, n in capacity.units_by_channel.items()}, {POOL: capacity.agent_call_slots}

    @staticmethod
    def _as_plan(decisions: Sequence[NbaDecision], rows: list[dict]) -> DailyPlan:
        status = {r["decision_id"]: r["status"] for r in rows}
        return DailyPlan(
            scheduled=[d for d in decisions if status[d.decision_id] == "scheduled"],
            deferred=[d for d in decisions if status[d.decision_id] == "deferred"],
        )

    def plan_daily_queue(self, decisions: Sequence[NbaDecision], capacity: ChannelCapacity) -> DailyPlan:
        # decisioning/allocator.py allocate(): highest expected value first, into channel units and agent call slots
        from decisioning import allocator

        rows = self._plan_rows(decisions)
        cap, slots = self._capacity_maps(capacity)
        allocator.allocate(rows, cap, slots)
        return self._as_plan(decisions, rows)

    def stress_test(self, plan: DailyPlan, capacity: ChannelCapacity, scenario: StressScenario) -> StressResult:
        # decisioning/stress_test.py rerun(): same allocator, channels down and fewer call slots; the real plan is
        # never touched. Moved means pushed to the next day (S6: the allocator defers, it does not re-route).
        from decisioning import stress_test

        everyone = [*plan.scheduled, *plan.deferred]
        before_ids = [(d.decision_id, d.action.channel) for d in plan.scheduled]
        rows = self._plan_rows(everyone)
        cap, slots = self._capacity_maps(capacity)
        kept = int(slots[POOL] * (1.0 - scenario.agent_absence_fraction))
        before, after = stress_test.rerun(
            rows, cap, slots, channels_down=set(scenario.channel_outages), slots_after={POOL: kept}
        )
        was = {r["decision_id"]: r["status"] for r in before}
        moved = [
            (r["decision_id"], "next_day")
            for r in after
            if r["status"] == "deferred" and was[r["decision_id"]] == "scheduled"
        ]
        return StressResult(
            plan=self._as_plan(everyone, after),
            moved=moved,
            original_unchanged=before_ids == [(d.decision_id, d.action.channel) for d in plan.scheduled],
        )

    # ---------------- labels ----------------
    def label_promise(self, promise: PromiseOutcome, ops_events: Sequence[OpsEvent], as_of: dt.date) -> int | None:
        # Mirrors pipeline/models/features/f_ptp_offline.sql: broken/partially_kept -> 1, kept -> 0, open and cancelled
        # excluded, promises due during a payment-posting outage dropped. The grace period is added here: a promise is
        # only broken once due date + grace days has passed.
        for ev in ops_events:
            if ev.payment_posting_affected and ev.start_ts.date() <= promise.due_date <= ev.end_ts.date():
                return None
        if promise.status in ("broken", "partially_kept"):
            return 1 if promise.due_date + dt.timedelta(days=promise.grace_days) <= as_of else None
        if promise.status == "kept":
            return 0
        return None

    # ---------------- promise check ----------------
    def check_promise(self, draft: PromiseDraft, payroll: PayrollInfo, case) -> PromiseCheck:
        # decisioning/promise_check.py: days_before_payday() and the LABEL; the live risk re-scores the promise with
        # the new due date (the promised amount is not a model input).
        from decisioning import promise_check

        today = self.business_date
        feats = {**case.features, "days_to_due_at_creation": (draft.due_date - today).days}
        p, _ = _score(feats)
        payday = payroll.customer_stated_income_date or payroll.expected_next_payroll_date
        return PromiseCheck(
            days_before_payday=promise_check.days_before_payday(draft.due_date, payday),
            break_probability=p,
            label=promise_check.LABEL,
            saved=False,
        )

    # ---------------- review batches ----------------
    def create_approval_batch(self, decisions: Sequence[NbaDecision]) -> ApprovalBatch:
        # decisioning/nba.py make_batches() rule: only batch-mode items ride in a batch, a 2% sample (rounded up,
        # at least one) is checked first; individual items are excluded and reviewed one by one.
        from decisioning import nba

        items = [d.decision_id for d in decisions if d.review_mode == "batch"]
        excluded = [d.decision_id for d in decisions if d.review_mode != "batch"]
        sample = random.Random(7).sample(items, nba.sample_size(len(items)))
        digest = items[0] if items else "EMPTY"
        return ApprovalBatch(
            batch_id=f"B-{digest}-{len(items)}",
            item_ids=items,
            sample_item_ids=sample,
            excluded_item_ids=excluded,
            status="pending",
        )


def _blank_case():
    from tests_spec.adapter import CaseSnapshot, CustomerContact

    return CaseSnapshot(case_id="GATE-ONLY", customer=CustomerContact(golden_id="GATE-ONLY"))


def _alt(a: dict):
    from decisioning.schemas import Action as OurAction

    return OurAction(treatment=a["action"]["treatment"], channel=a["action"]["channel"])
