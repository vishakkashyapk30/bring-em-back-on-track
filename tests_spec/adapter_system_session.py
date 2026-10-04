"""A signed-in person in the in-process system (`Session` in adapter.py), with role-based access control.

Roles are enforced the way the API does it (api/deps.require plus the row filters of v2 section 4): a role that may not
call an operation gets `PermissionError`; a call that is allowed but refused by a rule (a missing reason, a latch rule,
a batch whose sample was not checked) returns `ActionResult(allowed=False)`. Every write is audited through
governance/audit.py into the private ops database that `SpecSystemClient` owns.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import sqlite3
from typing import Any

from tests_spec import spec_constants as C
from tests_spec.adapter import (
    Action,
    ActionResult,
    ApprovalBatch,
    AreaObservation,
    C360Snapshot,
    CardTerms,
    CustomerView,
    Explanation,
    HardshipProgram,
    LoanTerms,
    MonitoringSnapshot,
    NbaDecision,
    PayrollInfo,
    PlanRequest,
    PromiseDraft,
    QueueItem,
    RecordedPromise,
    Transcript,
    TranscriptTurn,
    UserContext,
)
from tests_spec.adapter import Affordability as Afford
from tests_spec.adapter_l4_hardship import _eligibility_result
from tests_spec.adapter_system import (
    OUT_OF_HOURS_CODES,
    CaseCtx,
    DecisionRec,
    SpecSystemClient,
    to_date,
    to_dt,
)

SERVICING = ("agent", "hardship_specialist")
LEVEL_RANK = {"agent": 0, "hardship_specialist": 1, "team_lead": 2}  # who can sign off a plan offer


class SpecSession:
    def __init__(self, system: SpecSystemClient, user_id: str, role: str, team_id: str | None) -> None:
        self.sys = system
        self.user_id = user_id
        self.role = role
        self.team_id = team_id

    # ------------------------------------------------------------------ guards
    def _need(self, *roles: str) -> None:
        if self.role not in roles:
            raise PermissionError(f"Not available for the {self.role} role")

    def _may_see(self, ctx: CaseCtx) -> bool:
        if self.role == "agent":
            return ctx.agent_id == self.user_id
        if self.role == "team_lead":
            return ctx.team == self.team_id
        return self.role == "hardship_specialist"

    def _case(self, case_id: str) -> CaseCtx:
        ctx = self.sys.cases.get(case_id)
        if ctx is None:
            raise KeyError(f"no open case {case_id}")
        if not self._may_see(ctx):
            raise PermissionError("That case is not one of yours")
        return ctx

    def _rec(self, decision_id: str) -> DecisionRec:
        rec = self.sys.decisions.get(decision_id)
        if rec is None:
            raise KeyError(f"no decision {decision_id}")
        return rec

    def _can_act(self, rec: DecisionRec) -> None:
        """v2 section 4 and V1 section 6: an agent approves or overrides their own cases; a specialist the hardship ones."""
        if self.role == "agent" and rec.ctx.agent_id == self.user_id:
            return
        if self.role == "hardship_specialist" and rec.nba.route_to == "hardship_specialist":
            return
        raise PermissionError("Only the assigned agent (or a hardship specialist for hardship cases) can act on this")

    def _audit(self, event: str, entity_type: str, entity_id: str | None, inputs: Any = None, outputs: Any = None) -> str:
        return self.sys.audit(self.user_id, self.role, event, entity_type, entity_id, inputs, outputs)

    def _user(self) -> UserContext:
        return UserContext(self.user_id, self.role, self.team_id)  # type: ignore[arg-type]

    # ------------------------------------------------------------------ agent workspace
    def work_queue(self):
        self._need("agent", "hardship_specialist", "team_lead")
        items = []
        for rec in self.sys.decisions.values():
            a = rec.nba.action
            if rec.state != "proposed" or rec.stopped or a.treatment == "no_contact" or not self._may_see_queue(rec):
                continue
            items.append((rec.nba.expected_value or 0.0, QueueItem(
                decision_id=rec.decision_id, case_id=rec.nba.case_id, golden_id=rec.ctx.golden_id, action=a,
                review_mode=rec.nba.review_mode, explanation=rec.nba.explanation, assigned_agent_id=rec.ctx.agent_id)))
        return [i for _, i in sorted(items, key=lambda x: (-x[0], x[1].decision_id))]

    def _may_see_queue(self, rec: DecisionRec) -> bool:
        if self.role == "hardship_specialist":  # their worklist is the hardship cases
            return rec.nba.route_to == "hardship_specialist"
        return self._may_see(rec.ctx)

    def find_customer(self, source_system, source_key):
        gid = self.sys.gid_of.get((source_system, source_key))
        if gid is None:
            return None
        if self.role in ("agent", "team_lead") and not any(self._may_see(c) for c in self._cases_of(gid)):
            return None
        return gid

    def _cases_of(self, gid: str) -> list[CaseCtx]:
        return [c for c in self.sys.cases.values() if c.golden_id == gid]

    def open_customer(self, golden_id):
        if self.role == "data_steward":
            raise PermissionError("Stewards do not service customers")
        cases = self._cases_of(golden_id)
        if not cases:
            raise KeyError(f"no customer {golden_id}")
        if self.role in ("agent", "team_lead") and not any(self._may_see(c) for c in cases):
            raise PermissionError("That customer is not one of yours")
        ctx = cases[0]
        masked = self.role == "analyst"
        return self._view(ctx, masked)

    def _view(self, ctx: CaseCtx, masked: bool) -> CustomerView:
        s, gid = self.sys, ctx.golden_id
        gr = s.res.golden_records[gid]
        cluster = next(c for c in s.res.clusters if c.golden_id == gid)
        contact = s.customer_contact(ctx)
        nba = None if masked else s.propose(ctx, s.as_of)
        p = nba.break_probability if nba else None
        dep = ctx.deposit or {}
        name = gr.display_name or ""
        fields: dict[str, Any] = {
            "display_name": "".join(w[0] + "." for w in name.split()) if masked else name,
            "province_code": contact.province_code, "fsa": ctx.crm.get("fsa"), "time_zone": contact.time_zone,
            "preferred_language": ctx.crm.get("preferred_language"),
            **{f"consent_{ch}": v for ch, v in contact.consent.items()},
            "permitted_call_start_local": contact.permitted_call_start_local,
            "permitted_call_end_local": contact.permitted_call_end_local, "contact_block": contact.contact_block,
            "hardship_flag": contact.hardship_flag, "vulnerability_flag": contact.vulnerability_flag,
            "dispute_open_flag": contact.dispute_open_flag, "payroll_delay_days": dep.get("payroll_delay_days"),
            "max_dpd": ctx.dpd, "total_past_due_cad": ctx.overdue, "open_case_id": ctx.case["case_id"],
        }
        if not masked:
            fields.update(phone_token=gr.phone_token, email_token=gr.email_token)
        ids = {c["crm_customer_id"] for c in ctx.crm_all}
        timeline = sorted(({"date": str(h.get("contact_ts"))[:10], "type": h.get("channel_v2") or h.get("channel"),
                            "text": h.get("outcome") or "", "contact_id": h.get("contact_id")}
                           for h in s.t.get("contact_history", []) if h.get("crm_customer_id") in ids),
                          key=lambda x: x["date"], reverse=True)
        return CustomerView(
            golden_id=gid, fields=fields, masked_fields={"display_name"} if masked else set(),
            badges={"risk": {"score": None if p is None else round(p, 3), "band": nba.model_version if nba else None},
                    "bucket": ctx.case.get("dpd_bucket"),
                    "consent": {"call": (f"{contact.permitted_call_start_local}-{contact.permitted_call_end_local}"
                                         if contact.consent.get("call") else "no"),
                                **{ch: contact.consent.get(ch) for ch in ("sms", "email", "push")}},
                    "hardship": contact.hardship_flag},
            source_ids=list(cluster.members), match_confidence=cluster.match_confidence,
            lineage={"display_name": ["customers"], "consent": ["customers"], "max_dpd": ["card_accounts", "loan_accounts"],
                     "payroll_delay_days": ["deposit_accounts"],
                     "hardship_flag": ["collections_cases", "hardship_flag_events"], "source_ids": ["identity_xref"]},
            timeline=timeline, nba=nba)

    def approve_action(self, decision_id, note=None):
        rec = self._rec(decision_id)
        self._can_act(rec)
        if rec.state != "proposed" or rec.stopped:
            return ActionResult(False, rec.state, decision_id, reason="This proposal has already been dealt with")
        rec.state, rec.approved_by, rec.approved_via = "approved", self.user_id, "agent"
        aid = self._audit("nba_decision", "decision", decision_id,
                          {"decision_id": decision_id, "case_id": rec.nba.case_id, "note": note, "decision": "approve"},
                          {"action": dataclasses.asdict(rec.action)})
        return ActionResult(True, "approved", decision_id, aid)

    def override_action(self, decision_id, new_action, reason):
        rec = self._rec(decision_id)
        self._can_act(rec)
        if not (reason or "").strip():
            return ActionResult(False, "refused", decision_id, reason="An override needs a reason")
        if rec.state != "proposed" or rec.stopped:
            return ActionResult(False, rec.state, decision_id, reason="This proposal has already been dealt with")
        keep_at = new_action.scheduled_at or rec.nba.action.scheduled_at
        final = dataclasses.replace(new_action, scheduled_at=keep_at)
        if final.treatment != "no_contact":  # the policy gate is not something an override can switch off
            gate = self.sys.adapter.policy_gate(self.sys.customer_contact(rec.ctx), [final], keep_at or self.sys.as_of)
            if not gate.is_permitted(final):
                why = "; ".join(r.message for r in gate.rules_fired) or "the contact rules do not allow it"
                return ActionResult(False, "refused", decision_id, reason=why)
        before = dataclasses.asdict(rec.nba.action)
        rec.state, rec.final_action, rec.approved_by, rec.approved_via = "overridden", final, self.user_id, "agent"
        aid = self._audit("override", "decision", decision_id,
                          {"decision_id": decision_id, "case_id": rec.nba.case_id, "reason": reason, "from": before,
                           "to": dataclasses.asdict(final)}, {"final": dataclasses.asdict(final)})
        return ActionResult(True, "overridden", decision_id, aid)

    def check_promise(self, case_id, amount, due_date):
        self._need("agent", "hardship_specialist")
        ctx = self._case(case_id)
        pr = self.sys.open_promise(case_id) or {}
        dep = ctx.deposit or {}
        payroll = PayrollInfo(to_date(dep.get("expected_next_payroll_date")), to_date(pr.get("customer_stated_income_date")),
                              int(dep.get("payroll_delay_days") or 0))
        out = self.sys.adapter.check_promise(PromiseDraft(case_id, amount, due_date), payroll, self.sys.snapshot(ctx))
        self._audit("promise_check", "case", case_id, {"amount": amount, "due_date": due_date.isoformat()},
                    {"break_probability": out.break_probability, "days_before_payday": out.days_before_payday})
        return out

    def record_promise(self, case_id, amount, due_date):
        self._need("agent", "hardship_specialist")
        ctx = self._case(case_id)
        s = self.sys
        old = s.open_promise(case_id) or {}
        for p in s.promises(case_id):
            if p.get("ptp_status") == "open":
                p["ptp_status"] = "cancelled"  # the new promise replaces the one it moves
        s._promise_seq += 1
        pid = f"PTP-NEW-{s._promise_seq:04d}"
        s.t.setdefault("promises_to_pay", []).append({
            "ptp_id": pid, "case_id": case_id, "crm_customer_id": ctx.case.get("crm_customer_id"), "ptp_amount": amount,
            "ptp_due_date": due_date.isoformat(), "ptp_status": "open", "grace_days": old.get("grace_days", 2),
            "ptp_created_ts": s.as_of.isoformat(), "customer_stated_income_date": old.get("customer_stated_income_date")})
        aid = self._audit("promise_recorded", "case", case_id, {"amount": amount, "due_date": due_date.isoformat()},
                          {"ptp_id": pid, "replaced": old.get("ptp_id")})
        return ActionResult(True, "recorded", pid, aid)

    def post_call_summary(self, contact_id):
        self._need("agent", "hardship_specialist")
        s = self.sys
        contact = next((h for h in s.t.get("contact_history", []) if h.get("contact_id") == contact_id), None)
        tr = next((x for x in s.t.get("call_transcripts", []) if x.get("contact_id") == contact_id), None)
        if contact is None or tr is None:
            raise KeyError(f"no recorded call {contact_id}")
        gid = s._gid_of_crm(contact.get("crm_customer_id"))
        ctx = next(c for c in self._cases_of(gid))
        if not self._may_see(ctx):
            raise PermissionError("That call is not on one of your cases")
        turns = [TranscriptTurn(t["turn_index"], t["speaker"], t["text"]) for t in tr.get("turns", [])]
        transcript = Transcript(contact_id, ctx.case["case_id"], gid, turns, float(tr.get("asr_confidence_avg") or 0.95),
                                to_dt(tr.get("call_end_ts")))
        ptp = next((p for p in s.promises(ctx.case["case_id"]) if p.get("contact_id") == contact_id), None)
        recorded = RecordedPromise(ptp["ptp_id"], contact_id, ptp["ptp_amount"], to_date(ptp["ptp_due_date"])) if ptp else None
        draft = s.adapter.draft_post_call_summary(transcript, recorded)
        s.drafts[draft.draft_id] = (draft, ctx)
        self._audit("summary_draft", "contact", contact_id, {"contact_id": contact_id}, {"draft_id": draft.draft_id})
        return draft

    def approve_post_call_summary(self, draft_id, edits=None):
        self._need("agent", "hardship_specialist")
        draft, ctx = self.sys.drafts[draft_id]
        if not self._may_see(ctx):
            raise PermissionError("That call is not on one of your cases")
        from tests_spec.adapter import Actor

        # decisioning/post_call.approve is still TODO(WS-E): its NotImplementedError propagates and the test skips.
        res = self.sys.adapter.approve_post_call_summary(draft, Actor("person", self.user_id, self.role), edits)  # type: ignore[arg-type]
        return ActionResult(True, "approved", draft_id, str(res))

    def ask_policy(self, query):
        self._need("agent", "hardship_specialist", "team_lead")
        ans = self.sys.adapter.answer_policy_question(query, self._user())
        self._audit("query", "policy_question", None, {"question": query.question, "product": query.product},
                    {"answered": ans.answered, "citations": [dataclasses.asdict(c) for c in ans.citations]})
        return ans

    # ------------------------------------------------------------------ hardship workbench
    def _eligibility_inputs(self, ctx: CaseCtx):
        return self.sys.eligibility_row(ctx, self.sys.level(ctx.golden_id))

    def eligibility(self, golden_id):
        self._need("agent", "hardship_specialist")
        cases = self._cases_of(golden_id)
        if not cases:
            raise KeyError(f"no customer {golden_id}")
        if not any(self._may_see(c) for c in cases):
            raise PermissionError("That customer is not one of yours")
        from decisioning import eligibility

        ctx = cases[0]
        rows = eligibility.programs_for(self._eligibility_inputs(ctx), self.sys.programs(), [], self.sys.as_of.date(),
                                        self.sys.level(golden_id))
        rows.sort(key=lambda r: (not r["eligible"], r["program_id"]))
        return [_eligibility_result(r) for r in rows]

    def simulate_plan(self, case_id, program_id, levers):
        self._need("hardship_specialist")
        s = self.sys
        ctx = self._case(case_id)
        prow = next((p for p in s.programs() if p["program_id"] == program_id), None)
        if prow is None:
            raise KeyError(f"no program {program_id}")
        fields = {f.name for f in dataclasses.fields(HardshipProgram)}
        program = HardshipProgram(**{k: v for k, v in prow.items() if k in fields})
        card = next((a for a in ctx.accounts if "card_account_id" in a), None)
        loan = next((a for a in ctx.accounts if "loan_account_id" in a), None)
        if ctx.product == "card" and card:
            account: Any = CardTerms(card["card_account_id"], card["current_balance"], card["purchase_apr"],
                                     card["minimum_payment_due"])
        elif loan:
            account = LoanTerms(loan["loan_account_id"], loan["principal_balance"], loan["accrued_interest"],
                                loan["fees_outstanding"], loan["interest_rate"], loan["scheduled_payment_amount"],
                                loan["remaining_term_months"], loan.get("past_due_amount") or 0.0)
        else:
            raise ValueError("the case has no account to simulate on")
        dep = ctx.deposit or {}
        month_end = (s.as_of.date().replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
        # the seeded month-to-date amounts are month totals: they are scaled as for a full month
        aff = Afford(dep.get("payroll_avg_amount_3m") or 0.0, dep.get("essential_spend_amount_mtd") or 0.0,
                     dep.get("other_lender_payment_amount_mtd") or 0.0, month_end)
        from tests_spec.adapter import Actor

        req = PlanRequest(ctx.golden_id, account, program, levers, aff, float(ctx.case.get("total_exposure") or 0.0),
                          float(ctx.case.get("expected_loss_est") or 0.0), Actor("person", self.user_id, self.role))  # type: ignore[arg-type]
        sc = s.adapter.simulate_plan(req)  # decisioning/simulator; writes the simulator_run audit row
        from decisioning import eligibility

        ev = eligibility.programs_for(self._eligibility_inputs(ctx), [prow], [], s.as_of.date(), s.level(ctx.golden_id))
        sc.eligibility = _eligibility_result(ev[0]) if ev else None
        s.scenarios[sc.scenario_id] = {"ctx": ctx, "program": prow, "scenario": sc, "by": self.user_id}
        return sc

    def submit_plan_offer(self, scenario_id):
        self._need("hardship_specialist")
        rec = self.sys.scenarios.get(scenario_id)
        if rec is None:
            raise KeyError(f"no scenario {scenario_id}")
        sc = rec["scenario"]
        offer_id = f"OFFER-{scenario_id}"
        if sc.eligibility is not None and not sc.eligibility.eligible:
            aid = self._audit("plan_offer_refused", "offer", offer_id, {"scenario_id": scenario_id},
                              {"reason": "rules say not eligible"})
            return ActionResult(False, "refused", offer_id, aid, "The program rules say this customer is not eligible")
        needs = "team_lead" if not sc.within_program_rules else (sc.approver_level_required or "hardship_specialist")
        self.sys.offers[offer_id] = {"scenario_id": scenario_id, "needs": needs, "status": "pending_approval", **rec}
        aid = self._audit("plan_offer_submitted", "offer", offer_id, {"scenario_id": scenario_id},
                          {"status": "pending_approval", "approver_level_required": needs})
        return ActionResult(True, "pending_approval", offer_id, aid)

    def approve_plan_offer(self, offer_id):
        self._need("hardship_specialist", "team_lead")
        offer = self.sys.offers.get(offer_id)
        if offer is None:
            raise KeyError(f"no offer {offer_id}")
        if LEVEL_RANK.get(self.role, -1) < LEVEL_RANK.get(offer["needs"], 1):
            raise PermissionError(f"This offer needs a {offer['needs']} to sign it off")
        if offer["status"] != "pending_approval":
            return ActionResult(False, offer["status"], offer_id, reason="Already dealt with")
        s, ctx = self.sys, offer["ctx"]
        contact = s.customer_contact(ctx)
        cands = [Action("plan_offer", ch, scheduled_at=s.as_of, program_id=offer["program"]["program_id"])
                 for ch in ("call", "sms", "email")]
        gate = s.adapter.policy_gate(contact, cands, s.as_of)
        chosen = next((a for a in cands if gate.is_permitted(a)), None)
        offer["status"] = "approved"
        aid = self._audit("plan_offer_approved", "offer", offer_id, {"offer_id": offer_id},
                          {"channel": chosen.channel if chosen else None})
        if chosen is not None:  # the customer is told through the same sender as everything else
            nba = NbaDecision(offer_id, ctx.case["case_id"], chosen, None, None,
                              Explanation([], [], [], "Plan offer approved by a person", "template"), "individual")
            s.decisions[offer_id] = DecisionRec(nba, ctx, "scheduled", None, "approved", None, self.user_id, "offer")
        return ActionResult(True, "approved", offer_id, aid)

    def set_hardship_flag(self, golden_id, level, reason=None, program_id=None):
        self._need("agent", "hardship_specialist", "team_lead", "analyst", "data_steward")
        from tests_spec.adapter import Actor, HardshipState

        s = self.sys
        res = s.adapter.hardship_transition(HardshipState(golden_id, s.level(golden_id)),  # type: ignore[arg-type]
                                            level, Actor("person", self.user_id, self.role),  # type: ignore[arg-type]
                                            reason, program_id)
        if not res.accepted:
            return ActionResult(False, "refused", golden_id, reason=res.refusal_reason)
        return ActionResult(True, "applied", golden_id)

    def review_board(self):
        self._need("hardship_specialist")
        from tests_spec.adapter import ReviewBoardRow

        s = self.sys
        customers = []
        for gid in sorted({c.golden_id for c in s.cases.values()}):
            ctx = self._cases_of(gid)[0]
            customers.append({"golden_id": gid, "vulnerability_flag": ctx.crm.get("vulnerability_flag"),
                              "vulnerability_review_date": ctx.crm.get("vulnerability_review_date"),
                              "hardship_flag": s.level(gid), "hardship_source": ctx.case.get("hardship_source")})
        rows = s.adapter.review_board(customers, s.as_of.date())  # vulnerability reviews that are due
        seen = {r.golden_id for r in rows}
        # api/services/hardship.board(): customers flagged "possible" wait here for a person to confirm or clear
        rows += [ReviewBoardRow(c["golden_id"], to_date(c["vulnerability_review_date"]), "possible", c["hardship_source"])
                 for c in customers if c["hardship_flag"] == "possible" and c["golden_id"] not in seen]
        return rows

    def missed_offers(self):
        self._need("hardship_specialist")
        s = self.sys
        cases = [{"case_id": c.case["case_id"], "hardship_flag": s.level(c.golden_id),
                  "hardship_program_offered": c.case.get("hardship_program_offered"),
                  "case_open_date": c.case.get("case_open_date")} for c in s.cases.values()]
        return s.adapter.missed_offers(cases, s.t.get("offers", []))

    # ------------------------------------------------------------------ team lead
    def _batch(self, batch_id: str):
        b = self.sys.batches.get(batch_id)
        if b is None:
            raise KeyError(f"no batch {batch_id}")
        if b.team != self.team_id:
            raise PermissionError("That batch belongs to another team")
        return b

    def list_batches(self):
        self._need("team_lead")
        return [self._copy(b.batch) for b in self.sys.batches.values()
                if b.team == self.team_id and b.batch.status in ("pending", "sample_reviewed")]

    @staticmethod
    def _copy(b: ApprovalBatch) -> ApprovalBatch:
        return ApprovalBatch(b.batch_id, list(b.item_ids), list(b.sample_item_ids), list(b.excluded_item_ids), b.status)

    def mark_sample_reviewed(self, batch_id):
        self._need("team_lead")
        b = self._batch(batch_id)
        if b.batch.status == "approved":
            return ActionResult(False, "approved", batch_id, reason="Already approved")
        b.batch.status = "sample_reviewed"
        aid = self._audit("batch_sample_review", "batch", batch_id, {"batch_id": batch_id},
                          {"sample": list(b.batch.sample_item_ids)})
        return ActionResult(True, "sample_reviewed", batch_id, aid)

    def approve_batch(self, batch_id):
        self._need("team_lead")
        b = self._batch(batch_id)
        if b.batch.status != "sample_reviewed":
            return ActionResult(False, "refused", batch_id, reason="Check the sample first, then approve the batch")
        n = 0
        for did in b.batch.item_ids:
            rec = self.sys.decisions[did]
            if did in b.stopped or rec.state != "proposed":
                continue
            rec.state, rec.approved_by, rec.approved_via = "approved", self.user_id, "batch"
            n += 1
        b.batch.status, b.approved_by = "approved", self.user_id
        aid = self._audit("batch_approve", "batch", batch_id, {"batch_id": batch_id, "stopped": sorted(b.stopped)},
                          {"count": n})
        return ActionResult(True, "approved", batch_id, aid)

    def stop_batch_item(self, batch_id, item_id, reason):
        self._need("team_lead")
        b = self._batch(batch_id)
        if item_id not in b.batch.item_ids:
            return ActionResult(False, "refused", item_id, reason="That item is not in this batch")
        if not (reason or "").strip():
            return ActionResult(False, "refused", item_id, reason="Stopping an item needs a reason")
        b.stopped.add(item_id)
        rec = self.sys.decisions[item_id]
        rec.stopped = True  # also stops an item whose batch was approved but not yet sent
        aid = self._audit("batch_item_stopped", "decision", item_id, {"batch_id": batch_id, "reason": reason},
                          {"status": "stopped"})
        self._audit("batch_item_stopped", "batch", batch_id, {"item_id": item_id, "reason": reason}, {"status": "stopped"})
        return ActionResult(True, "stopped", item_id, aid)

    def _proposed(self, rows):
        from tests_spec.adapter import ProposedAction

        return [ProposedAction(r["proposal_id"], r["kind"], r["subject_id"], r["status"], r["requires_role"],
                               r["requires_policy_office_signoff"]) for r in rows]

    def playbook_proposals(self):
        """decisioning/playbooks.py: what the radar and the outage shield propose; they wait for a team lead."""
        from decisioning import playbooks

        self._need("team_lead")
        with self.sys.adapter._ops_scope():
            return self._proposed(playbooks.listing())

    def approve_proposal(self, proposal_id):
        from decisioning import playbooks

        self._need("team_lead")
        with self.sys.adapter._ops_scope():
            try:
                res = playbooks.approve(proposal_id, self.user_id, self.role, self.team_id)
            except KeyError:
                return ActionResult(False, "refused", proposal_id, reason="No such proposal")
            except ValueError as e:
                return ActionResult(False, "refused", proposal_id, reason=str(e))
        return ActionResult(True, "approved", proposal_id, str(res["audit_id"]))

    def run_stress_test(self, scenario):
        self._need("team_lead", "analyst")
        s = self.sys
        res = s.adapter.stress_test(s.plan, s.capacity, scenario)
        self._audit("stress_test", "plan", None, {"scenario": scenario.name, "channel_outages": scenario.channel_outages},
                    {"moved": len(res.moved)})
        return res

    def monitoring(self):
        """governance/monitoring.snapshot (production code) bound to the in-memory system's decisions and sent log."""
        from governance import monitoring

        self._need("team_lead", "analyst")
        s = self.sys
        recs = [{"approved_via": r.approved_via if r.state in ("approved", "overridden", "sent", "blocked") else None,
                 "proposed": r.nba.action, "final": r.final_action} for r in s.decisions.values()]
        sent = []
        for m in s.sent_log:
            act, c = m["action"], m["contact"]
            sent.append({"treatment": act.treatment, "channel": act.channel, "hardship_flag": c.hardship_flag,
                         "vulnerability_flag": c.vulnerability_flag, "contacts_last_7d": c.contacts_last_7d,
                         "contact_cap_7d": c.contact_cap_7d, "_contact": c, "_action": act, "_at": m["at"]})

        def out_of_hours(m):
            free = dataclasses.replace(m["_contact"], hardship_flag="none", vulnerability_flag=False, contacts_last_7d=0)
            g = s.adapter.policy_gate(free, [m["_action"]], m["_at"])
            return any(code in OUT_OF_HOURS_CODES for _a, code in g.blocked)

        snap = monitoring.snapshot(decisions=recs, sent=sent, refusals=s.refusals, out_of_hours=out_of_hours,
                                   with_warehouse=False)
        return MonitoringSnapshot(
            override_rate=snap["override_rate"], override_review_triggered=snap["override_review_triggered"],
            pressure_on_hardship_count=snap["pressure_on_hardship_count"],
            contact_cap_breach_count=snap["contact_cap_breach_count"],
            out_of_hours_contact_count=snap["out_of_hours_contact_count"],
            refusal_count=snap["refusal_count"],
            extra={"decisions_reviewed": snap["decisions_reviewed"], "overrides": snap["overrides"]})

    # ------------------------------------------------------------------ analyst
    def ask(self, question, token_overrides=None):
        self._need("analyst", "team_lead")
        ans = self.sys.adapter.ask(question, self._user(), token_overrides)
        self._audit("query", "question", None, {"question": question},
                    {"refused": ans.refused, "data_products": ans.data_products, "rows": len(ans.rows or [])})
        if ans.refused:
            self.sys.refusals += 1
            self._audit("refusal", "question", None, {"question": question}, {"reason": ans.refusal_reason})
        return ans

    def employer_radar(self):
        self._need("analyst", "team_lead")
        from tests_spec.adapter import RadarRow

        return [RadarRow(r["employer_key"], r["n_customers"], r["n_payroll_gap"], r["n_new_ei"], r["pattern"],
                         r["explained_by_incident"], r["open_cases"], r["exposure_cad"], r["label"])
                for r in self.sys.radar_rows]

    def weather_map(self):
        self._need("analyst", "team_lead")
        s = self.sys
        obs = []
        for gid in sorted({c.golden_id for c in s.cases.values()}):
            ctx = self._cases_of(gid)[0]
            broken = any(p.get("ptp_status") in ("broken", "partially_kept") for p in s.promises(ctx.case["case_id"]))
            obs.append(AreaObservation(gid, ctx.crm.get("fsa") or "", broken, False))
        return s.adapter.weather_map(obs)

    def strategy_scorecard(self):
        self._need("analyst", "team_lead")
        return self.sys.adapter.strategy_scorecard(self.sys.t.get("collections_cases", []))

    # ------------------------------------------------------------------ data steward
    def identity_review_queue(self):
        self._need("data_steward")
        done = self.sys.identity_decisions
        return [dataclasses.replace(i, decided=i.item_id in done) for i in self.sys.res.review_queue]

    def decide_identity_review(self, item_id, link, reason):
        self._need("data_steward")
        if item_id not in self.sys.review:
            return ActionResult(False, "refused", item_id, reason="No such review item")
        if not (reason or "").strip():
            return ActionResult(False, "refused", item_id, reason="A decision needs a reason")
        self.sys.identity_decisions[item_id] = {"link": link, "reason": reason, "by": self.user_id}
        aid = self._audit("identity_review", "identity_review", item_id, {"link": link, "reason": reason},
                          {"verdict": "link" if link else "no_link"})
        return ActionResult(True, "decided", item_id, aid)

    def data_quality_report(self):
        self._need("data_steward", "analyst", "team_lead")
        s = self.sys
        gids = sorted(s.res.golden_records)
        customers, crm_current, accounts = [], [], []
        for gid in gids:
            g, case = s.res.golden_records[gid], next(iter(self._cases_of(gid)), None)
            crm = [s.crm_rows[c] for c in g.crm_customer_ids if c in s.crm_rows]
            customers.append({
                "golden_id": gid, "crm_customer_ids": g.crm_customer_ids, "match_method": g.match_method,
                "match_confidence": g.match_confidence, "display_name": g.display_name, "phone_token": g.phone_token,
                "email_token": g.email_token, "province_code": crm[0].get("province_code"), "fsa": crm[0].get("fsa"),
                "time_zone": crm[0].get("time_zone"), "preferred_language": crm[0].get("preferred_language"),
                **{f"consent_{ch}": all(bool(r.get(f"consent_{ch}")) for r in crm) for ch in C.CONSENT_CHANNELS},
                "permitted_call_start_local": max(str(r.get("permitted_call_start_local") or "08:00") for r in crm),
                "permitted_call_end_local": min(str(r.get("permitted_call_end_local") or "20:00") for r in crm),
                "contact_block": "none", "hardship_flag": s.level(gid) if case else "none",
                "vulnerability_flag": any(bool(r.get("vulnerability_flag")) for r in crm), "dispute_open_flag": False,
                "max_dpd": case.dpd if case else 0, "total_past_due_cad": case.overdue if case else 0.0,
                "open_case_id": case.case["case_id"] if case else None, "_refreshed_at": s.as_of})
            crm_current += [{"crm_customer_id": r["crm_customer_id"], "golden_id": gid,
                             "national_id_hash": r.get("national_id_hash"),
                             **{f"consent_{ch}": bool(r.get(f"consent_{ch}")) for ch in C.CONSENT_CHANNELS}} for r in crm]
        for c in s.res.clusters:
            accounts += [{"account_id": m.split(":", 1)[1], "golden_id": c.golden_id, "party_role": "primary"}
                         for m in c.members if m.split(":", 1)[0] in ("cards", "loans", "deposits")]
        events = [{"golden_id": e["golden_id"], "from_level": e["from_level"], "to_level": e["to_level"],
                   "reviewer": e["reviewer_id"], "reason": e["reason"]} for e in self._hardship_events_all()]
        snap = C360Snapshot({"c360_customer": customers, "crm_current": crm_current, "c360_account": accounts,
                             "hardship_flag_events": events, "employer_match_sample": []})
        return s.adapter.run_quality_rules(snap, s.as_of)

    def _hardship_events_all(self) -> list[dict[str, Any]]:
        from common.db import ops

        with self.sys.adapter._ops_scope(), ops() as con:
            return [dict(r) for r in con.execute("SELECT * FROM hardship_flag_events ORDER BY event_id").fetchall()]

    def drift_fixes(self):
        from governance import drift
        from tests_spec.adapter import ProposedFix

        self._need("data_steward")
        with self.sys.adapter._ops_scope():
            return [ProposedFix(f["fix_id"], f["description"], f["status"], f["applied"]) for f in drift.fixes()]

    def approve_drift_fix(self, fix_id):
        from governance import drift

        self._need("data_steward")
        with self.sys.adapter._ops_scope():
            try:
                res = drift.approve_fix(fix_id, self.user_id, self.role)
            except KeyError:
                return ActionResult(False, "refused", fix_id, reason="No such fix")
            except ValueError as e:
                return ActionResult(False, "refused", fix_id, reason=str(e))
        return ActionResult(True, "approved", fix_id, str(res["audit_id"]))

    # ------------------------------------------------------------------ governance
    def audit_log(self, event_type=None, subject_id=None):
        return self.sys.adapter.audit_log(event_type, subject_id)

    def delete_audit_record(self, audit_id):
        """There is no delete operation. The attempt goes to the table itself, where the append-only triggers
        (common/ops_schema.sql) refuse it, and the refusal is returned."""
        from common.db import ops

        try:
            with self.sys.adapter._ops_scope(), ops() as con:
                n = con.execute("DELETE FROM audit_log WHERE audit_id = ?", (int(audit_id),)).rowcount
            if n == 0:
                return ActionResult(False, "refused", audit_id, reason="No such audit record")
        except sqlite3.DatabaseError as e:
            return ActionResult(False, "refused", audit_id, reason=str(e))
        return ActionResult(True, "deleted", audit_id)
