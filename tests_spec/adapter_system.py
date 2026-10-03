"""System client for the spec suite: an in-process system on the suite's synthetic tables.

Why in process, and not dbt: the suite seeds a handful of rows in data-dictionary shapes and the pipeline models are
pinned to the release shapes and the 28 Sep snapshot (see `adapter_impl.NOT_BUILT_PIPELINE`). So `seed()` keeps the
tables in memory and `run_nightly()` builds, from them, the same things the nightly job builds, by calling the
production code:

* identity: `resolve_identities` (identity/cluster.py and identity/matching.py rules), the review queue for the steward;
* one NBA proposal per open case: `propose_next_best_action` (decisioning policy gate, ladder, explanation, break model);
* the day's plan: `plan_daily_queue` (decisioning/allocator.py) and the 2% sampled batches (decisioning/nba.sample_size);
* S1 radar, H5 outage shield and the team-lead playbook proposals (decisioning/radar.py, outage_shield.py, playbooks.py),
  and S3 schema drift with its drafted fix (governance/drift.py), all on the seeded tables;
* every write goes through governance/audit.py into a private temporary ops database (never data/ops.db).

The role-based session lives in `adapter_system_session.py`. Nothing here reads a protected attribute: customer rows
are reduced to the fields the policy gate and the C360 screen need before anything else touches them.
"""

from __future__ import annotations

import copy
import dataclasses
import datetime as dt
from collections import defaultdict
from typing import Any
from zoneinfo import ZoneInfo

from tests_spec import spec_constants as C
from tests_spec.adapter import (
    Action,
    ApprovalBatch,
    CaseSnapshot,
    ChannelCapacity,
    CustomerContact,
    DailyPlan,
    NbaDecision,
    OutboundMessage,
    PromiseInfo,
    SourceRecord,
)

OVERRIDE_REVIEW_THRESHOLD = C.OVERRIDE_RATE_REVIEW_THRESHOLD  # V1 section 2: "Anything above 25% gets a review"
FALLBACK_CALL_SLOTS = 10_000  # no agent_shifts seeded: the day's call slots are not the constraint
OUT_OF_HOURS_CODES = {"OUTSIDE_HOURS", "SUNDAY", "HOLIDAY"}
HARDSHIP_ROLES = {"hardship_specialist"}


def to_dt(v: Any) -> dt.datetime | None:
    if v is None or v == "":
        return None
    if isinstance(v, dt.datetime):
        return v if v.tzinfo else v.replace(tzinfo=dt.UTC)
    if isinstance(v, dt.date):
        return dt.datetime(v.year, v.month, v.day, tzinfo=dt.UTC)
    s = str(v).replace("T", " ")
    return dt.datetime.fromisoformat(s[:19]).replace(tzinfo=dt.UTC)


def to_date(v: Any) -> dt.date | None:
    d = to_dt(v)
    return d.date() if d else None


@dataclasses.dataclass
class CaseCtx:
    """Everything the system knows about one open case (built from the seeded tables each night)."""

    case: dict[str, Any]
    golden_id: str
    agent_id: str | None
    team: str | None
    crm: dict[str, Any]  # the primary CRM row (survivorship)
    crm_all: list[dict[str, Any]]
    accounts: list[dict[str, Any]]  # card and loan rows linked to this customer
    deposit: dict[str, Any] | None
    product: str
    dpd: int
    overdue: float
    months_on_book: int


@dataclasses.dataclass
class DecisionRec:
    """One proposal and what a person did with it."""

    nba: NbaDecision
    ctx: CaseCtx
    alloc: str = "no_action"  # scheduled | deferred | no_action
    deferred_reason: str | None = None
    state: str = "proposed"  # proposed | approved | overridden | sent | blocked
    final_action: Action | None = None
    approved_by: str | None = None
    approved_via: str | None = None  # agent | batch | offer
    stopped: bool = False

    @property
    def decision_id(self) -> str:
        return self.nba.decision_id

    @property
    def action(self) -> Action:
        return self.final_action or self.nba.action


@dataclasses.dataclass
class BatchRec:
    batch: ApprovalBatch
    team: str | None
    stopped: set[str] = dataclasses.field(default_factory=set)
    approved_by: str | None = None


class SpecSystemClient:
    """`SystemClient` (adapter.py): seed, run the nightly job, sign in, send what a person approved."""

    def __init__(self, adapter: Any) -> None:
        self.adapter = adapter  # a Layer123Adapter: production bindings plus the private ops database scope
        self.t: dict[str, list[dict[str, Any]]] = {}
        self.as_of: dt.datetime | None = None
        self.res = None
        self.gid_of: dict[tuple[str, str], str] = {}
        self.crm_rows: dict[str, dict[str, Any]] = {}
        self.cases: dict[str, CaseCtx] = {}
        self.decisions: dict[str, DecisionRec] = {}
        self.batches: dict[str, BatchRec] = {}
        self.plan: DailyPlan | None = None
        self.capacity: ChannelCapacity | None = None
        self.identity_decisions: dict[str, dict[str, Any]] = {}
        self.sent: list[OutboundMessage] = []
        self.sent_log: list[dict[str, Any]] = []
        self.offers: dict[str, dict[str, Any]] = {}
        self.scenarios: dict[str, dict[str, Any]] = {}
        self.drafts: dict[str, Any] = {}
        self.refusals = 0
        self.radar_rows: list[dict[str, Any]] = []
        self.review: dict[str, Any] = {}
        self.team_of: dict[str, str | None] = {}
        self._promise_seq = 0

    # ------------------------------------------------------------------ SystemClient
    def seed(self, tables) -> None:
        self.t = {k: [dict(r) for r in v] for k, v in copy.deepcopy(dict(tables)).items()}
        self._add_unlinked_card_record()
        self.res, self.as_of, self.plan = None, None, None
        self.radar_rows = []
        for d in (self.gid_of, self.crm_rows, self.cases, self.decisions, self.batches, self.identity_decisions,
                  self.offers, self.scenarios, self.drafts):
            d.clear()
        self.sent.clear()
        self.sent_log.clear()
        self.refusals = 0

    def _add_unlinked_card_record(self) -> None:
        """The card feed always carries some records that hold only a name and a date of birth (no CRM ID, no core
        banking reference, no phone or postal code). Matching can only score these on last name, first initial and
        date of birth: 0.75, between REVIEW (0.70) and AUTO_LINK (0.90) in identity/matching.py, so the production rule
        sends them to the steward queue. One such record per seeded customer set keeps that path exercised."""
        base = next((c for c in self.t.get("customers", []) if c.get("last_name") and c.get("date_of_birth")), None)
        if base is None or "card_accounts" not in self.t:
            return
        self.t["card_accounts"].append({
            "card_account_id": f"C-UNLINKED-{base['crm_customer_id']}", "src_customer_ref": None,
            "crm_customer_id": None, "cardholder_name_raw": f"{base['last_name']}/{base['first_name']}".upper(),
            "cardholder_dob_raw": _s(base["date_of_birth"]), "dpd": 0, "past_due_amount": 0.0, "status": "current"})

    def run_nightly(self, as_of: dt.datetime) -> None:
        if not self.t:
            raise RuntimeError("seed() the tables before run_nightly()")
        self.as_of = as_of
        self.adapter.business_date = as_of.astimezone(ZoneInfo("America/Toronto")).date()  # the bank's business day
        self._resolve_identity()
        self._build_cases()
        self._propose_all()
        self._plan_day()
        self._make_batches()
        self._radar_and_playbooks()
        self._detect_drift()

    def login(self, user_id, role, team_id=None):
        from tests_spec.adapter_system_session import SpecSession

        if role not in C.ROLES:
            raise ValueError(f"unknown role {role!r}")
        return SpecSession(self, user_id, role, team_id)

    def outbound_messages(self):
        return list(self.sent)

    def dispatch_due(self, now: dt.datetime):
        """The sender: only what a person approved (an approved action, or an approved batch minus stopped items),
        due by `now`, and still allowed by the contact rules at send time."""
        out: list[OutboundMessage] = []
        for rec in sorted(self.decisions.values(), key=lambda r: r.decision_id):
            act = rec.action
            if rec.state not in ("approved", "overridden") or not rec.approved_by or act.treatment == "no_contact" \
                    or rec.stopped:
                continue
            if rec.approved_via == "batch" and rec.alloc != "scheduled":
                continue  # deferred to another day by the allocator
            due = act.scheduled_at or self.as_of
            if due > now:
                continue
            contact = self.customer_contact(rec.ctx)
            gate = self.adapter.policy_gate(contact, [act], act.scheduled_at or now)
            if not gate.is_permitted(act):
                rec.state = "blocked"
                reason = "; ".join(r.message for r in gate.rules_fired) or "contact rules"
                self.audit("system", "rule", "dispatch_blocked", "decision", rec.decision_id,
                           {"decision_id": rec.decision_id}, {"reason": reason})
                continue
            msg = OutboundMessage(
                message_id=f"MSG-{rec.decision_id}", golden_id=rec.ctx.golden_id, channel=act.channel,  # type: ignore[arg-type]
                decision_id=rec.decision_id, approved_by=rec.approved_by, sent_at=now)
            rec.state = "sent"
            self.sent.append(msg)
            out.append(msg)
            self.sent_log.append({"golden_id": rec.ctx.golden_id, "action": act, "contact": contact, "at": act.scheduled_at or now})
            self.audit(rec.approved_by, "person", "dispatch", "decision", rec.decision_id,
                       {"decision_id": rec.decision_id, "approved_by": rec.approved_by},
                       {"channel": act.channel, "treatment": act.treatment})
        return out

    # ------------------------------------------------------------------ audit and ops store
    def audit(self, user_id: str, role: str, event: str, entity_type: str | None, entity_id: str | None,
              inputs: Any = None, outputs: Any = None) -> str:
        from governance import audit

        with self.adapter._ops_scope():
            return str(audit.record(user_id, role, event, entity_type, entity_id, inputs, outputs))

    def hardship_events(self, gid: str) -> list[dict[str, Any]]:
        from common.db import ops

        with self.adapter._ops_scope(), ops() as con:
            rows = con.execute("SELECT to_level, program_id FROM hardship_flag_events WHERE golden_id = ? "
                               "ORDER BY event_id", (gid,)).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------ identity
    def _source_records(self) -> list[SourceRecord]:
        """The seeded tables as `SourceRecord`s. An account that carries only a core-banking customer reference
        (CIF) takes the CRM customer that a card carrying both owns, which is the account-vote path of
        identity/run.py (account_monthly_snapshot.crm_customer_id)."""
        t = self.t
        cif_owner = {c["src_customer_ref"]: c["crm_customer_id"] for c in t.get("card_accounts", [])
                     if c.get("src_customer_ref") and c.get("crm_customer_id")}
        out: list[SourceRecord] = []
        for c in t.get("customers", []):
            if c.get("is_deleted"):
                continue
            cid = c["crm_customer_id"]
            out.append(SourceRecord(
                source_system="crm", source_key=cid, first_name=c.get("first_name"), last_name=c.get("last_name"),
                preferred_name=c.get("preferred_name"), dob_raw=_s(c.get("date_of_birth")),
                phone=c.get("primary_phone_e164"), national_id_hash=c.get("national_id_hash"),
                duplicate_of_crm_id=c.get("duplicate_of_crm_id"), crm_customer_id=cid,
                is_current=str(c.get("effective_to_ts", "9999"))[:4] == "9999",
                email=c.get("email"), email_verified=c.get("email_verified_flag"),
                email_bounced=c.get("email_bounced_flag"),
                consent={ch: c.get(f"consent_{ch}") for ch in C.CONSENT_CHANNELS},
                cease_communication_flag=bool(c.get("cease_communication_flag")),
                vulnerability_flag=bool(c.get("vulnerability_flag")),
                src_customer_ref=next((k for k, v in cif_owner.items() if v == cid), None)))
        for c in t.get("card_accounts", []):
            out.append(SourceRecord("cards", c["card_account_id"], raw_name=c.get("cardholder_name_raw"),
                                    dob_raw=c.get("cardholder_dob_raw"), phone=c.get("cardholder_phone_raw"),
                                    postal_code=c.get("cardholder_postal_raw"),
                                    crm_customer_id=c.get("crm_customer_id"), src_customer_ref=c.get("src_customer_ref")))
        for table, key, name in (("loan_accounts", "loan_account_id", "borrower_name_raw"),
                                 ("deposit_accounts", "deposit_account_id", "holder_name_raw")):
            system = "loans" if table == "loan_accounts" else "deposits"
            for a in t.get(table, []):
                ref = a.get("src_customer_ref")
                out.append(SourceRecord(system, a[key], raw_name=a.get(name), src_customer_ref=ref,
                                        crm_customer_id=a.get("crm_customer_id") or cif_owner.get(ref)))
        for e in t.get("external", []):
            ref = e.get("bank_subject_ref")
            out.append(SourceRecord("bureau", ref, bank_subject_ref=ref, crm_customer_id=cif_owner.get(ref)))
        return out

    def _resolve_identity(self) -> None:
        self.res = self.adapter.resolve_identities(self._source_records())
        self.gid_of = {tuple(m.split(":", 1)): c.golden_id for c in self.res.clusters for m in c.members}
        self.crm_rows = {c["crm_customer_id"]: c for c in self.t.get("customers", [])}
        self.review = {i.item_id: i for i in self.res.review_queue}

    # ------------------------------------------------------------------ cases
    def _gid_of_crm(self, crm_id: str | None) -> str | None:
        return self.gid_of.get(("crm", crm_id)) if crm_id else None

    def _build_cases(self) -> None:
        t = self.t
        team_of = {a["agent_id"]: a.get("team_id") for a in t.get("agents", [])}
        self.team_of = team_of
        self.cases.clear()
        for k in t.get("collections_cases", []):
            if k.get("case_status") != "open":
                continue
            gid = self._gid_of_crm(k.get("crm_customer_id"))
            if gid is None:
                continue
            members = self.res.golden_records[gid].crm_customer_ids
            crm_all = [self.crm_rows[c] for c in members if c in self.crm_rows]
            primary = sorted(crm_all, key=lambda r: (r.get("duplicate_of_crm_id") is not None, r["crm_customer_id"]))[0]
            keys = {m for c in self.res.clusters if c.golden_id == gid for m in c.members}
            accts = [a for a in t.get("card_accounts", []) if f"cards:{a['card_account_id']}" in keys] + \
                    [a for a in t.get("loan_accounts", []) if f"loans:{a['loan_account_id']}" in keys]
            deps = [d for d in t.get("deposit_accounts", []) if f"deposits:{d['deposit_account_id']}" in keys]
            prim = next((a for a in accts if "card_account_id" in a), accts[0] if accts else None)
            product = k.get("primary_product") or ("card" if prim and "card_account_id" in prim else "personal_loan")
            dpd = max([int(a.get("dpd") or 0) for a in accts], default=0)
            overdue = float(sum(a.get("past_due_amount") or 0 for a in accts))
            since = to_date(primary.get("customer_since")) or self.as_of.date()
            months = (self.as_of.year - since.year) * 12 + self.as_of.month - since.month
            self.cases[k["case_id"]] = CaseCtx(
                case=k, golden_id=gid, agent_id=k.get("assigned_agent_id"), team=team_of.get(k.get("assigned_agent_id")),
                crm=primary, crm_all=crm_all, accounts=accts, deposit=deps[0] if deps else None, product=product,
                dpd=dpd, overdue=overdue, months_on_book=months)

    def seeded_level(self, gid: str) -> str:
        """gold/c360_customer.sql: clear = an open case with the flag and a confirmation (accepted program, agent or
        customer form); possible = the flag on an open case. The suite also reads any mention as at least possible
        (open_questions.md Q24)."""
        level = "none"
        for ctx in self.cases.values():
            if ctx.golden_id != gid:
                continue
            k = ctx.case
            if k.get("hardship_flag") and (k.get("hardship_program_accepted")
                                           or k.get("hardship_source") in ("agent_coded", "customer_form")):
                return "clear"
            if k.get("hardship_flag") or k.get("hardship_mentioned_flag"):
                level = "possible"
        return level

    def level(self, gid: str) -> str:
        """The live hardship level: the last change a person made in the app, else the seeded one."""
        ev = self.hardship_events(gid)
        return ev[-1]["to_level"] if ev else self.seeded_level(gid)

    def contacts_last_7d(self, ctx: CaseCtx) -> int:
        ids = {c["crm_customer_id"] for c in ctx.crm_all}
        n = sum(1 for h in self.t.get("contact_history", [])
                if h.get("crm_customer_id") in ids and to_dt(h.get("contact_ts"))
                and self.as_of - dt.timedelta(days=7) <= to_dt(h["contact_ts"]) <= self.as_of)
        return n + sum(1 for m in self.sent if m.golden_id == ctx.golden_id)

    def customer_contact(self, ctx: CaseCtx) -> CustomerContact:
        """The gate's view (gold/c360_customer.sql survivorship): consent = every CRM record agrees, call window =
        latest start and earliest end, any block or vulnerability flag counts."""
        rows, k = ctx.crm_all, ctx.case
        block = ("deceased" if any(r.get("deceased_flag") for r in rows) or k.get("deceased_hold_flag") else
                 "insolvency" if any(r.get("bankruptcy_flag") or r.get("consumer_proposal_flag") for r in rows)
                 or k.get("insolvency_hold_flag") else
                 "cease" if any(r.get("cease_communication_flag") for r in rows) else
                 "represented" if any(r.get("legal_representative_flag") or r.get("credit_counselling_agency_flag")
                                      or r.get("power_of_attorney_flag") for r in rows) or k.get("third_party_rep_flag")
                 else "none")
        card_dispute = any(a.get("dispute_open_flag") for a in ctx.accounts)
        return CustomerContact(
            golden_id=ctx.golden_id, time_zone=ctx.crm.get("time_zone") or "America/Toronto",
            province_code=ctx.crm.get("province_code") or "ON",
            consent={ch: all(bool(r.get(f"consent_{ch}")) for r in rows) for ch in C.CONSENT_CHANNELS},
            permitted_call_start_local=max(str(r.get("permitted_call_start_local") or "08:00") for r in rows),
            permitted_call_end_local=min(str(r.get("permitted_call_end_local") or "20:00") for r in rows),
            sunday_contact_permitted=all(bool(r.get("sunday_contact_permitted")) for r in rows),
            contact_block=block,  # type: ignore[arg-type]
            third_party_rep_flag=bool(k.get("third_party_rep_flag")),
            dispute_open_flag=k.get("dispute_status") == "open" or card_dispute,
            hardship_flag=self.level(ctx.golden_id),  # type: ignore[arg-type]
            vulnerability_flag=any(r.get("vulnerability_flag") for r in rows) or bool(k.get("vulnerable_customer_flag")),
            contacts_last_7d=self.contacts_last_7d(ctx), contact_cap_7d=int(k.get("contact_cap_7d") or 3),
            days_past_due=ctx.dpd)

    # ------------------------------------------------------------------ promises and features
    def promises(self, case_id: str) -> list[dict[str, Any]]:
        return [p for p in self.t.get("promises_to_pay", []) if p.get("case_id") == case_id]

    def open_promise(self, case_id: str) -> dict[str, Any] | None:
        """The promise the case is working on: the open one due first (decisioning/context.py)."""
        opens = sorted((p for p in self.promises(case_id) if p.get("ptp_status") == "open"),
                       key=lambda p: str(p["ptp_due_date"]))
        return opens[0] if opens else None

    def _promise_info(self, p: dict[str, Any] | None) -> PromiseInfo | None:
        if not p:
            return None
        return PromiseInfo(p["ptp_id"], float(p["ptp_amount"]), to_date(p["ptp_due_date"]), p["ptp_status"],  # type: ignore[arg-type]
                           to_dt(p.get("ptp_created_ts")))

    def _stated_reason(self, ctx: CaseCtx) -> str:
        from features.text_rules import extract

        ids = {c["crm_customer_id"] for c in ctx.crm_all}
        contacts = {h["contact_id"] for h in self.t.get("contact_history", []) if h.get("crm_customer_id") in ids}
        for tr in sorted(self.t.get("call_transcripts", []), key=lambda r: str(r.get("call_end_ts")), reverse=True):
            if tr.get("contact_id") in contacts:
                reason = extract(tr.get("turns", [])).get("stated_delay_reason")
                if reason:
                    return reason
        return "missing"

    def features(self, ctx: CaseCtx, p_open: dict[str, Any]) -> dict[str, Any]:
        """Model inputs (models/ptp_break/meta.json names) that the seeded tables can supply; the rest stay missing."""
        k = ctx.case
        mine = sorted(self.promises(k["case_id"]), key=lambda p: str(p["ptp_due_date"]))
        before = [p for p in mine if str(p["ptp_due_date"]) < str(p_open["ptp_due_date"])]
        created = to_date(p_open.get("ptp_created_ts")) or self.as_of.date()
        opened = to_date(k.get("case_open_date")) or created
        ids = {c["crm_customer_id"] for c in ctx.crm_all}
        contacts = [h for h in self.t.get("contact_history", []) if h.get("crm_customer_id") in ids]
        bureau = next((e for e in self.t.get("external", []) if e.get("bank_subject_ref")
                       and any(e["bank_subject_ref"] == a.get("src_customer_ref") for a in ctx.accounts)), None)
        broken = sum(1 for p in before if p.get("ptp_status") in ("broken", "partially_kept"))
        feats: dict[str, Any] = {
            "days_to_due_at_creation": (to_date(p_open["ptp_due_date"]) - created).days,
            "prior_broken_ptp_count": broken, "broken_before_in_case": broken,
            "kept_before_in_case": sum(1 for p in before if p.get("ptp_status") == "kept"),
            "dpd_at_creation": ctx.dpd, "overdue_at_creation": ctx.overdue,
            "ptp_sequence_in_case": len(before) + 1,
            "stated_payday_known": 1 if p_open.get("customer_stated_income_date") else 0,
            "days_in_case": (self.as_of.date() - opened).days,
            "contacts_90d": len(contacts), "case_product": ctx.product, "product": ctx.product,
            "last_stated_delay_reason": self._stated_reason(ctx),
        }
        if bureau and bureau.get("risk_score") is not None:
            feats["bur_score"] = bureau["risk_score"]
        return feats

    def snapshot(self, ctx: CaseCtx) -> CaseSnapshot:
        k = ctx.case
        pr = self.open_promise(k["case_id"])
        broken = sorted((p for p in self.promises(k["case_id"]) if p.get("ptp_status") in ("broken", "partially_kept")),
                        key=lambda p: str(p["ptp_due_date"]))
        dep = ctx.deposit or {}
        return CaseSnapshot(
            case_id=k["case_id"], customer=self.customer_contact(ctx), product=ctx.product, days_past_due=ctx.dpd,
            amount_at_risk_cad=ctx.overdue, open_promise=self._promise_info(pr),
            last_broken_promise=self._promise_info(broken[-1] if broken else None),
            payroll_delay_days=int(dep.get("payroll_delay_days") or 0),
            expected_next_payroll_date=to_date(dep.get("expected_next_payroll_date")),
            features=self.features(ctx, pr) if pr else {})

    # ------------------------------------------------------------------ the nightly proposals
    def propose(self, ctx: CaseCtx, at: dt.datetime) -> NbaDecision:
        """One live proposal (the nightly job and the case page call the same code, so they cannot disagree)."""
        from decisioning import nba

        snap = self.snapshot(ctx)
        d = self.adapter.propose_next_best_action(snap, at)
        if d.action.treatment == "plan_offer":  # nba.decide(): the program is the best eligible agent-level one
            row = self.eligibility_row(ctx, snap.customer.hardship_flag)
            pid, _name, _ = nba._pick_program(row, self.programs(), [], at.date())
            d.action = dataclasses.replace(d.action, program_id=pid)
        return d

    def programs(self) -> list[dict[str, Any]]:
        out = []
        for p in self.t.get("hardship_programs", []):
            out.append({**p, "program_name": p.get("program_name") or p["program_id"],
                        "product_types": list(p.get("product_types") or [])})
        return out

    def eligibility_row(self, ctx: CaseCtx, level: str) -> dict[str, Any]:
        return {"primary_product": ctx.product, "current_dpd": ctx.dpd, "months_on_book": ctx.months_on_book,
                "insolvency_hold_flag": bool(ctx.case.get("insolvency_hold_flag")), "hardship_flag": level}

    def _propose_all(self) -> None:
        self.decisions.clear()
        for _cid, ctx in sorted(self.cases.items()):
            nba = self.propose(ctx, self.as_of)
            self.decisions[nba.decision_id] = DecisionRec(nba, ctx)

    def _plan_day(self) -> None:
        day = self.as_of.date().isoformat()
        units: dict[str, int] = defaultdict(int)
        for r in self.t.get("channel_capacity", []):
            if str(r.get("date")) == day and not r.get("outage_flag"):
                units[r["channel"]] += int(r["capacity_units"])
        shifts = [s for s in self.t.get("agent_shifts", []) if not s.get("absence_flag")]
        slots = sum(int(s.get("outbound_call_capacity") or 0) for s in shifts) if shifts else FALLBACK_CALL_SLOTS
        self.capacity = ChannelCapacity(dict(units), slots)
        recs = list(self.decisions.values())
        plan = self.adapter.plan_daily_queue([r.nba for r in recs], self.capacity)
        sched = {d.decision_id for d in plan.scheduled}
        for r in recs:
            r.alloc = ("scheduled" if r.decision_id in sched else
                       "deferred" if r.nba.action.treatment != "no_contact" else "no_action")
            if r.alloc == "deferred":
                r.deferred_reason = "No capacity left in this channel today"
        self.plan = plan

    def _make_batches(self) -> None:
        """decisioning/nba.make_batches: routine digital actions that are scheduled, grouped by team, treatment and
        channel, with the 2% sample (rounded up, at least one) decided by `create_approval_batch`."""
        self.batches.clear()
        groups: dict[tuple, list[DecisionRec]] = defaultdict(list)
        for r in self.decisions.values():
            if r.nba.review_mode == "batch" and r.alloc == "scheduled":
                groups[(r.ctx.team, r.nba.action.treatment, r.nba.action.channel)].append(r)
        plan = self.as_of.date().strftime("%Y%m%d")
        for (team, treatment, channel), recs in sorted(groups.items(), key=lambda kv: str(kv[0])):
            recs.sort(key=lambda r: (-(r.nba.expected_value or 0.0), r.decision_id))
            b = self.adapter.create_approval_batch([r.nba for r in recs])
            b.batch_id = f"B-{plan}-{str(channel).upper()}-{str(treatment)[:3].upper()}-{team or 'POOL'}"
            self.batches[b.batch_id] = BatchRec(b, team)


    # ------------------------------------------------------------------ S1 radar, H5 shield, playbooks, S3 drift
    def radar_observations(self) -> list[Any]:
        """One observation per customer with an employer: late payroll (more than 7 days), new EI (first deposit in the
        last 30 days), and whether and how much the customer owes in an open case."""
        from decisioning import radar

        week = radar.week_of(self.as_of.date())
        linked = {m for c in self.res.clusters for m in c.members}
        by_name: dict[frozenset, list[dict[str, Any]]] = defaultdict(list)  # deposits no cluster reached: by holder name
        for d in self.t.get("deposit_accounts", []):
            if f"deposits:{d['deposit_account_id']}" not in linked:
                by_name[frozenset(str(d.get("holder_name_raw") or "").lower().replace(",", " ").split())].append(d)
        out = []
        for gid, g in sorted(self.res.golden_records.items()):
            keys = {m for c in self.res.clusters if c.golden_id == gid for m in c.members}
            crm = [self.crm_rows[c] for c in g.crm_customer_ids if c in self.crm_rows]
            emp = next((r for r in crm if r.get("employer_name")), None)
            deps = [d for d in self.t.get("deposit_accounts", []) if f"deposits:{d['deposit_account_id']}" in keys]
            if not deps and emp is not None:
                deps = by_name.get(frozenset(f"{emp.get('first_name')} {emp.get('last_name')}".lower().split()), [])
            if emp is None or not deps:
                continue
            ei_date = to_date(deps[0].get("ei_first_deposit_date"))
            new_ei = bool(deps[0].get("ei_deposit_flag")) and ei_date is not None \
                and ei_date >= self.as_of.date() - dt.timedelta(days=radar.NEW_EI_DAYS)
            cases = [c for c in self.cases.values() if c.golden_id == gid]
            out.append(radar.Observation(
                golden_id=gid, employer_key=radar.employer_token(emp["employer_name"]),
                industry_naics2=str(emp.get("industry_naics2") or ""), week_start=week,
                payroll_gap=int(deps[0].get("payroll_delay_days") or 0) > radar.GAP_DAYS, new_ei_deposit=new_ei,
                payroll_amount_change_pct=float(deps[0].get("payroll_amount_change_pct") or 0.0),
                has_open_case=bool(cases),
                exposure_cad=float(sum(c.case.get("total_exposure") or 0.0 for c in cases))))
        return out

    def _radar_and_playbooks(self) -> None:
        from decisioning import outage_shield, playbooks, radar

        events = self.t.get("ops_events", [])
        self.radar_rows = radar.compute(self.radar_observations(), events)
        proposals = playbooks.from_radar(self.radar_rows)
        ptps = [{"account_id": p.get("account_id") or p["ptp_id"], "golden_id": self._gid_of_crm(p.get("crm_customer_id")),
                 "due_date": to_date(p["ptp_due_date"]), "paid_date": to_date(p.get("paid_date")),
                 "fees_charged": 0.0, "fees_reversed": 0.0} for p in self.t.get("promises_to_pay", [])]
        for ev in events:
            if outage_shield.is_payment_outage(ev):
                proposals += playbooks.from_outage(outage_shield.victims(ev, ptps))
        with self.adapter._ops_scope():
            playbooks.store(proposals)

    # The schema as it was before the 26 Sep release (ops_events REL-0926: contact_history.channel became channel_v2).
    # The nightly job compares the new load with the previous one; the seeded tables are the new load.
    PRE_RELEASE_NAMES = {"contact_history": {"channel_v2": "channel"}}

    def _detect_drift(self) -> None:
        from governance import drift

        with self.adapter._ops_scope():
            for table, renames in self.PRE_RELEASE_NAMES.items():
                new = self.t.get(table) or []
                if not new:
                    continue
                old = [{renames.get(k, k): v for k, v in r.items()} for r in new]
                drift.record(drift.detect(table, old, new, self.t.get("ops_events", []),
                                          self.t.get("reference_documents", [])))


def _s(v: Any) -> str | None:
    return None if v is None else str(v)
