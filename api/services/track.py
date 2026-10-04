# ruff: noqa: E501
"""Track: each persona follows ONE subject over time (docs/reference/track_inbox_watchlist.md).

* Agent: one of their own customers (a case assigned to them) -> one chronological timeline across accounts, cases,
  promises, contacts, notes, calls and recordings, hardship flag events, NBA decisions and post-call summaries.
* Hardship specialist: a customer open to them by row scope -> the hardship journey (signals, flag events, offers,
  eligibility, simulated plans, plan survival).
* Team lead: an agent on their team, or an employer from the radar (aggregates, groups under 10 hidden).
* Analyst: a cohort of cases (opened in a month or week, a province or FSA, a strategy code or a product), aggregates
  only with small-group suppression; never an individual customer.
* Steward: a golden customer's identity (lineage, never calls or notes) or a data product.

Authorisation is decided by `authorize` BEFORE any data is read (api/access.py row scope for customers and
identities). The warehouse is opened read-only. Nothing here writes, except `propose_test`, which stores a proposal
through the existing playbook store and writes the audit log (governance.audit.record). Every other action in a
tracker calls an existing endpoint (NBA decision, summary approval, hardship flag, batch and playbook approval,
identity verdict, drift fix approval), each of which writes the audit log itself.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from decimal import Decimal
from typing import Any

from fastapi import HTTPException

from api import access
from api.schemas.common import Session
from api.schemas.track import (
    Action,
    Event,
    Fact,
    Insight,
    KindInfo,
    Kinds,
    Line,
    Proposed,
    Section,
    Series,
    Source,
    Subject,
    SubjectList,
    Table,
    TrackView,
)
from api.services.c360 import PRODUCT_LABEL, SYSTEM_LABEL, _meta
from common.config import get_settings
from common.db import ops, warehouse
from governance import audit

ROLE_KINDS: dict[str, list[str]] = {
    "agent": ["customer"],
    "hardship_specialist": ["customer"],
    "team_lead": ["agent", "employer"],
    "analyst": ["cohort"],
    "steward": ["identity", "product"],
}
KIND_INFO = {
    "customer": ("Customer", "One customer's full history over time."),
    "agent": ("Agent", "An agent on your team: promises kept, overrides, contacts, guardrails, queue."),
    "employer": ("Employer", "An employer from the radar: late payroll and EI over time (groups under 10 hidden)."),
    "cohort": ("Cohort", "Cases opened in a month or week, a province or FSA, a strategy or a product. Aggregates only."),
    "identity": ("Customer identity", "How one golden ID was built: sources, match confidence, reviews."),
    "product": ("Data product", "A table: lineage, contract tests, quality issues and schema drift."),
}
RECENT_DAYS = 30
PROVINCES = ("AB", "BC", "MB", "NB", "NL", "NS", "NT", "NU", "ON", "PE", "QC", "SK", "YT")
CASE_PRODUCTS = ("card", "personal_loan", "overdraft", "auto_loan", "loc", "mortgage")
CASE_PRODUCT_LABEL = {**PRODUCT_LABEL, "overdraft": "Overdraft", "loc": "Line of credit"}
EMPLOYER_KEY = re.compile(r"^EMP-[0-9A-F]{8}$")
GOLDEN = re.compile(r"^G-[A-Z0-9]{3,12}$")
AGENT_ID = re.compile(r"^AG-\d{3,6}$")
EMP_HASH = "'EMP-' || upper(substr(md5(lower(trim(c.employer_name))), 1, 8))"
CHANNEL_LABEL = {"sms": "SMS", "email": "Email", "push": "App notification", "call": "Call", "letter": "Letter", "system": "System event",
                 "ivr": "Phone menu", "chat": "Chat"}
SYSTEM_TABLES = {"crm": "customers", "cards": "card_accounts", "lending": "loan_accounts",
                 "core_banking": "deposit_accounts", "bureau": "external", "collections": "collections_cases"}


# ------------------------------------------------------------------ small helpers
def _role(s: Session) -> str:
    return getattr(s.role, "value", str(s.role))


def _min_group() -> int:
    return get_settings().suppression_min_group


def _as_of() -> dt.date:
    return get_settings().as_of_date


def _deny(reason: str, code: int = 403) -> HTTPException:
    return HTTPException(code, detail={"reason": reason})


def _flat(sql: str) -> str:
    return " ".join(sql.split())


def _sql_src(label: str, sql: str) -> Source:
    return Source(kind="sql", label=label, sql=_flat(sql))


def _rec_src(label: str, table: str, ids: list[Any]) -> Source:
    return Source(kind="records", label=label, table=table, ids=[str(i) for i in ids if i is not None][:25])


def _iso(v: Any) -> str:
    if v is None or v != v:
        return ""
    return str(v)[:19].replace(" ", "T")


def _day(v: Any) -> str:
    return _iso(v)[:10]


def _cad(v: Any) -> str:
    return "n/a" if v is None else f"${float(v):,.0f}"


def _pct(v: Any, digits: int = 0) -> str:
    return "n/a" if v is None else f"{float(v) * 100:.{digits}f}%"


def _short(name: str | None) -> str:
    p = (name or "").split()
    return f"{p[0][0]}. {p[-1]}" if len(p) >= 2 else (name or "Customer")


def _py(v: Any) -> Any:
    return float(v) if isinstance(v, Decimal) else v


class _W:
    """One read-only warehouse connection for a whole view (search path silver, gold like Ask)."""

    def __enter__(self) -> _W:
        self.con = warehouse(read_only=True)
        self.con.execute("SET search_path='silver,gold'")
        return self

    def __exit__(self, *exc: Any) -> None:
        self.con.close()

    def q(self, sql: str, params: list | None = None) -> list[dict[str, Any]]:
        rel = self.con.execute(sql, params or [])
        cols = [d[0] for d in rel.description]
        return [dict(zip(cols, map(_py, r), strict=True)) for r in rel.fetchall()]


def _ops(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    with ops() as con:
        return [dict(r) for r in con.execute(sql, params).fetchall()]


def _months_back(n: int = 12) -> list[str]:
    """The last n calendar months up to the snapshot month, oldest first, as YYYY-MM."""
    d = _as_of().replace(day=1)
    out = []
    for _ in range(n):
        out.append(d.strftime("%Y-%m"))
        d = (d - dt.timedelta(days=1)).replace(day=1)
    return out[::-1]


# ------------------------------------------------------------------ authorisation (before any data is read)
def kinds_for(s: Session) -> list[str]:
    return ROLE_KINDS.get(_role(s), [])


def _check_kind(s: Session, kind: str) -> None:
    if kind not in KIND_INFO:
        raise _deny("Unknown subject type.", 404)
    if kind not in kinds_for(s):
        raise _deny(f"Tracking a {KIND_INFO[kind][0].lower()} is not available for the {_role(s).replace('_', ' ')} role.")


def authorize(s: Session, kind: str, id_: str) -> None:
    """Raise 403/404/422 unless this person may track this subject. Runs before any of the subject's data is read."""
    _check_kind(s, kind)
    if kind == "customer":
        if not GOLDEN.match(id_):
            raise _deny("That is not a golden customer ID.", 422)
        access.golden(s, id_)  # agent: a case assigned to them; specialist: the hardship row rule (docs/reference/row_scope.md)
    elif kind == "identity":
        if not GOLDEN.match(id_):
            raise _deny("That is not a golden customer ID.", 422)
        access.lineage(s, id_)  # stewards see identity lineage only, never calls or notes
    elif kind == "agent":
        if not AGENT_ID.match(id_) or not _agent_on_team(s, id_):
            raise _deny("This agent is not on your team.")
    elif kind == "employer":
        if not EMPLOYER_KEY.match(id_):
            raise _deny("That is not an employer key.", 422)
        if _employer_size(id_) < _min_group():
            raise _deny(f"Employers with fewer than {_min_group()} customers are hidden (small-group suppression).")
    elif kind == "cohort":
        parse_cohort(id_)
    elif kind == "product":
        if id_ not in _products():
            raise _deny("That data product is not in the catalog.", 404)


def _agent_on_team(s: Session, agent_id: str) -> bool:
    if not s.team_id:
        return False
    with _W() as w:
        r = w.q("SELECT 1 AS ok FROM silver.agents WHERE agent_id = ? AND team_id = ?", [agent_id, s.team_id])
    return bool(r)


MEMBERS_SQL = f"""SELECT DISTINCT g.golden_id, c.crm_customer_id FROM silver.customers c
    JOIN identity.crm_golden g USING (crm_customer_id)
    WHERE c.employer_name IS NOT NULL AND c.effective_to_ts >= TIMESTAMP '9999-01-01' AND {EMP_HASH} = ?"""


def _employer_size(key: str) -> int:
    with _W() as w:
        return int(w.q(f"SELECT count(DISTINCT golden_id) AS n FROM ({MEMBERS_SQL})", [key])[0]["n"])


# ------------------------------------------------------------------ cohorts (validated, then inlined so the SQL shown is complete)
def parse_cohort(cid: str) -> dict[str, str]:
    """`month:2026-06`, `week:2026-09-14` (a Monday), `province:ON`, `fsa:N9A`, `strategy:MID-CALL-HEAVY`,
    `product:card`. Every value is checked against a pattern or an allowlist before it reaches SQL."""
    dim, _, val = cid.partition(":")
    bad = _deny("Unknown cohort. Use month:YYYY-MM, week:YYYY-MM-DD (a Monday), province:XX, fsa:A1A, "
                "strategy:CODE or product:NAME.", 422)
    if dim == "month" and re.fullmatch(r"20\d\d-(0[1-9]|1[0-2])", val):
        start = dt.date.fromisoformat(val + "-01")
        end = (start + dt.timedelta(days=32)).replace(day=1)
        label = f"Cases opened in {start.strftime('%B %Y')}"
        where = f"c.case_open_date >= DATE '{start}' AND c.case_open_date < DATE '{end}'"
    elif dim == "week" and re.fullmatch(r"20\d\d-\d\d-\d\d", val):
        try:
            start = dt.date.fromisoformat(val)
        except ValueError as e:
            raise bad from e
        if start.weekday() != 0:
            raise _deny("A week cohort starts on a Monday.", 422)
        label = f"Cases opened in the week of {start.strftime('%d %b %Y')}"
        where = f"c.case_open_date >= DATE '{start}' AND c.case_open_date < DATE '{start + dt.timedelta(days=7)}'"
    elif dim == "province" and val in PROVINCES:
        label, where = f"Cases in {val}", f"c.province_code = '{val}'"
    elif dim == "fsa" and re.fullmatch(r"[A-Z]\d[A-Z]", val):
        label = f"Cases of customers in postal area {val}"
        where = f"c.case_id IN (SELECT k.case_id FROM c360_case k JOIN c360_customer u ON u.golden_id = k.golden_id WHERE u.fsa = '{val}')"
    elif dim == "strategy" and re.fullmatch(r"[A-Z][A-Z0-9-]{1,40}", val):
        label, where = f"Cases on strategy {val}", f"c.strategy_code = '{val}'"
    elif dim == "product" and val in CASE_PRODUCTS:
        label, where = f"{CASE_PRODUCT_LABEL.get(val, val)} cases", f"c.primary_product = '{val}'"
    else:
        raise bad
    return {"dim": dim, "value": val, "label": label, "where": where}


# ------------------------------------------------------------------ data products (steward)
def _manifest() -> dict:
    from pathlib import Path

    p = Path(__file__).resolve().parents[2] / "pipeline" / "target" / "manifest.json"
    return json.loads(p.read_text()) if p.exists() else {"nodes": {}, "parent_map": {}, "child_map": {}}


def _products() -> dict[str, str]:
    """schema.table -> dbt unique_id, for every model in the dbt project (gold, silver, features)."""
    out = {}
    for uid, n in _manifest().get("nodes", {}).items():
        if uid.startswith("model.") and n.get("schema"):
            out[f"{n['schema']}.{n['name']}"] = uid
    return out


# ------------------------------------------------------------------ kinds, suggestion and the picker
def kinds(s: Session) -> Kinds:
    ks = [KindInfo(kind=k, label=KIND_INFO[k][0], hint=KIND_INFO[k][1]) for k in kinds_for(s)]
    sug, sk = None, None
    try:
        sk, sug = suggest(s)
    except Exception:  # a suggestion is a convenience; the picker still works without it
        sug = None
    return Kinds(role=_role(s), kinds=ks, suggested=sug, suggested_kind=sk if sug else None)


def suggest(s: Session) -> tuple[str | None, Subject | None]:
    """The subject the guided demo starts from: the demo journey's customer where the person may open it."""
    role = _role(s)
    if role in ("agent", "hardship_specialist", "steward"):
        from decisioning.assistant.journey import sample_customer

        c = sample_customer()
        kind = "identity" if role == "steward" else "customer"
        if c:
            try:
                authorize(s, kind, c["golden_id"])
                label = c["name"] if role == "agent" else (_short(c["name"]) if role == "hardship_specialist" else c["golden_id"])
                return kind, Subject(id=c["golden_id"], label=label, sublabel=f"Case {c['case_id']} (the guided demo's customer)")
            except HTTPException:
                pass
        items = subjects(s, kind, "").items
        return kind, (items[0] if items else None)
    if role == "team_lead":
        items = subjects(s, "agent", "").items
        pick = next((i for i in items if i.id == "AG-6274"), items[0] if items else None)
        return "agent", pick
    if role == "analyst":
        m = (_as_of().replace(day=1) - dt.timedelta(days=95)).strftime("%Y-%m")
        return "cohort", Subject(id=f"month:{m}", label=parse_cohort(f"month:{m}")["label"], sublabel="Matured: every case has had 90 days")
    return None, None


def subjects(s: Session, kind: str, q: str = "", limit: int = 40) -> SubjectList:
    """Picker list, scoped to the person (the same row rules as api/access.py)."""
    _check_kind(s, kind)
    q = (q or "").strip()[:60]
    like = f"%{q.lower()}%"
    role = _role(s)
    if kind == "customer" and role == "agent":
        with _W() as w:
            rows = w.q("""SELECT k.golden_id, any_value(u.display_name) AS name, count(*) AS cases,
                              max(CASE WHEN k.case_status = 'open' THEN k.case_id END) AS open_case,
                              max(k.current_dpd) FILTER (WHERE k.case_status = 'open') AS dpd,
                              bool_or(k.hardship_flag) AS hardship, max(k.case_open_date) AS opened
                       FROM c360_case k JOIN c360_customer u ON u.golden_id = k.golden_id
                       WHERE k.assigned_agent_id = ?
                         AND (? = '' OR lower(u.display_name) LIKE ? OR lower(k.golden_id) LIKE ? OR lower(k.case_id) LIKE ?)
                       GROUP BY k.golden_id ORDER BY (open_case IS NULL), opened DESC LIMIT ?""",
                       [s.user_id, q, like, like, like, limit])
        return SubjectList(kind=kind, note="Customers with a case assigned to you.", items=[
            Subject(id=r["golden_id"], label=r["name"] or r["golden_id"],
                    sublabel=" · ".join(x for x in [r["golden_id"], r["open_case"] and f"open case {r['open_case']}",
                                                    r["dpd"] is not None and f"{r['dpd']} days past due"] if x),
                    badges=["Hardship"] if r["hardship"] else []) for r in rows])
    if kind == "customer" and role == "hardship_specialist":
        flagged = [r["golden_id"] for r in _ops("""SELECT golden_id FROM hardship_flag_events e WHERE event_id = (SELECT max(event_id)
                                                      FROM hardship_flag_events x WHERE x.golden_id = e.golden_id) AND to_level <> 'none'""")][:500]
        extra = f" OR k.golden_id IN ({','.join('?' * len(flagged))})" if flagged else ""
        pred = f"(k.case_id IN (SELECT case_id FROM collections_cases WHERE {access._SPECIALIST_SQL}){extra})"
        with _W() as w:
            rows = w.q(f"""SELECT k.golden_id, any_value(u.display_name) AS name, any_value(u.hardship_flag) AS level,
                               any_value(u.vulnerability_flag) AS vulnerable,
                               max(CASE WHEN k.case_status = 'open' THEN k.case_id END) AS open_case
                        FROM c360_case k JOIN c360_customer u ON u.golden_id = k.golden_id
                        WHERE {pred} AND (? = '' OR lower(k.golden_id) LIKE ? OR lower(k.case_id) LIKE ? OR lower(u.display_name) LIKE ?)
                        GROUP BY k.golden_id
                        ORDER BY (any_value(u.hardship_flag) = 'possible') DESC, (open_case IS NULL), k.golden_id LIMIT ?""",
                       [s.user_id, s.team_id, *flagged, q, like, like, like, limit])
        return SubjectList(kind=kind, note="On the hardship board, flagged hardship or vulnerable, or assigned to you or your team.", items=[
            Subject(id=r["golden_id"], label=_short(r["name"]),
                    sublabel=" · ".join(x for x in [r["golden_id"], r["open_case"] and f"open case {r['open_case']}"] if x),
                    badges=[b for b in [r["level"] != "none" and f"Hardship {r['level']}", r["vulnerable"] and "Vulnerable"] if b])
            for r in rows])
    if kind == "agent":
        with _W() as w:
            rows = w.q("""SELECT agent_id, agent_display_name AS name, role, current_case_load, max_concurrent_cases,
                              ptp_kept_rate_90d FROM silver.agents
                       WHERE team_id = ? AND status = 'active' AND role <> 'team_lead'
                         AND (? = '' OR lower(agent_display_name) LIKE ? OR lower(agent_id) LIKE ?)
                       ORDER BY agent_id LIMIT ?""", [s.team_id, q, like, like, limit])
        return SubjectList(kind=kind, note=f"Agents on team {s.team_id}.", items=[
            Subject(id=r["agent_id"], label=r["name"], sublabel=f"{r['agent_id']} · {r['role'].replace('_', ' ')} · load {r['current_case_load']} of {r['max_concurrent_cases']}")
            for r in rows])
    if kind == "employer":
        rows = _radar_rows()
        rows = [r for r in rows if not q or q.lower() in r["employer_key"].lower() or q.lower() in str(r.get("industry_naics2") or "").lower()]
        rows.sort(key=lambda r: (r["pattern"] == "none", -float(r.get("gap_rate") or 0)))
        return SubjectList(kind=kind, note=f"Employers with at least {_min_group()} customers (smaller ones are hidden). Names are not shown.", items=[
            Subject(id=r["employer_key"], label=r["employer_key"],
                    sublabel=f"Industry {r.get('industry_naics2') or 'n/a'} · {r['n_customers']} customers · {r.get('open_cases', 0)} open cases",
                    badges=[] if r["pattern"] == "none" else [r["pattern"].replace("_", " ")]) for r in rows[:limit]])
    if kind == "cohort":
        return SubjectList(kind=kind, items=_cohort_options(q), note="Aggregates only. Groups under 10 customers are hidden.")
    if kind == "identity":
        with _W() as w:
            if q:
                rows = w.q("""SELECT golden_id, match_method, match_confidence, source_systems FROM c360_customer
                              WHERE golden_id LIKE ? ORDER BY golden_id LIMIT ?""", [f"{q.upper()}%", limit])
            else:
                rows = w.q("""SELECT u.golden_id, u.match_method, u.match_confidence, u.source_systems FROM c360_customer u
                              WHERE u.golden_id IN (SELECT candidate_golden_id FROM identity.review_queue ORDER BY score DESC, pair_id LIMIT ?)
                              ORDER BY u.golden_id""", [limit])
        return SubjectList(kind=kind, note="Search by golden ID. Without a search: customers with a grey-band match waiting for review. Names are never shown.", items=[
            Subject(id=r["golden_id"], label=r["golden_id"],
                    sublabel=f"{r['match_method']} match · confidence {float(r['match_confidence']):.3f} · {r['source_systems']} source systems")
            for r in rows])
    if kind == "product":
        names = sorted(_products())
        names = [n for n in names if not q or q.lower() in n.lower()]
        order = {"gold": 0, "features": 1, "silver": 2}
        names.sort(key=lambda n: (order.get(n.split(".")[0], 3), n))
        return SubjectList(kind=kind, note="Every table built by the dbt project.", items=[
            Subject(id=n, label=n, sublabel={"gold": "Data product", "features": "Feature table", "silver": "Typed source table"}.get(n.split(".")[0]))
            for n in names[:limit]])
    raise _deny("Unknown subject type.", 404)


def _cohort_options(q: str) -> list[Subject]:
    months = _months_back(12)[::-1]
    opts = [Subject(id=f"month:{m}", label=parse_cohort(f"month:{m}")["label"], sublabel="By month opened") for m in months]
    monday = _as_of() - dt.timedelta(days=_as_of().weekday())
    opts += [Subject(id=f"week:{monday - dt.timedelta(weeks=i)}", label=parse_cohort(f"week:{monday - dt.timedelta(weeks=i)}")["label"],
                     sublabel="By week opened") for i in range(6)]
    opts += [Subject(id=f"province:{p}", label=f"Cases in {p}", sublabel="By province") for p in PROVINCES]
    opts += [Subject(id=f"product:{p}", label=f"{CASE_PRODUCT_LABEL.get(p, p)} cases", sublabel="By product") for p in CASE_PRODUCTS]
    with _W() as w:
        strategies = [r["strategy_code"] for r in w.q("SELECT strategy_code FROM collections_cases WHERE strategy_code IS NOT NULL GROUP BY 1 ORDER BY count(*) DESC")]
    opts += [Subject(id=f"strategy:{st}", label=f"Cases on strategy {st}", sublabel="By strategy") for st in strategies]
    qq = q.strip().upper()
    if re.fullmatch(r"[A-Z]\d[A-Z]", qq):
        opts.insert(0, Subject(id=f"fsa:{qq}", label=f"Cases of customers in postal area {qq}", sublabel="By postal area (FSA)"))
    if q:
        opts = [o for o in opts if q.lower() in (o.label + " " + o.id).lower()]
    return opts


def _radar_rows() -> list[dict]:
    from decisioning import radar
    from decisioning.assistant import data

    out = data.ttl_cached(("track_radar",), 600, lambda: radar.employer_week(limit=100_000))
    return out.get("rows", [])


# ------------------------------------------------------------------ dispatch
def view(s: Session, kind: str, id_: str) -> TrackView:
    authorize(s, kind, id_)
    role = _role(s)
    if kind == "customer":
        return _specialist_customer(s, id_) if role == "hardship_specialist" else _agent_customer(s, id_)
    if kind == "agent":
        return _lead_agent(s, id_)
    if kind == "employer":
        return _lead_employer(s, id_)
    if kind == "cohort":
        return _analyst_cohort(s, id_)
    if kind == "identity":
        return _steward_identity(s, id_)
    return _steward_product(s, id_)


# ------------------------------------------------------------------ shared customer reads
def _customer_records(w: _W, g: str) -> dict[str, Any]:
    cust = w.q("""SELECT golden_id, display_name, city, province_code, segment, hardship_flag, vulnerability_flag,
                         dispute_open_flag, contact_block, open_case_id, max_dpd, total_past_due_cad FROM c360_customer WHERE golden_id = ?""", [g])
    if not cust:
        raise _deny("No customer with that ID.", 404)
    cases = w.q("""SELECT case_id, case_open_date, case_status, case_status_date, primary_product, entry_dpd, current_dpd,
                          current_bucket, total_overdue, cure_flag, cure_date, hardship_flag, hardship_source, hardship_reason,
                          hardship_program_offered, hardship_program_accepted, strategy_code, assigned_agent_id, assigned_team,
                          outcome, outcome_date, human_override_flag, override_reason, contacts_last_7d, contact_cap_7d,
                          payments_since_open_amount, payments_since_open_count, current_ptp_id, current_ptp_amount, current_ptp_due_date
                   FROM c360_case WHERE golden_id = ? ORDER BY case_open_date""", [g])
    ids = [c["case_id"] for c in cases] or ["-"]
    ph = ",".join("?" * len(ids))
    rec: dict[str, Any] = {"customer": cust[0], "cases": cases, "case_ids": ids, "ph": ph}
    rec["promises"] = w.q(f"""SELECT ptp_id, case_id, ptp_created_ts, ptp_amount, ptp_due_date, ptp_status, status_ts,
                                     amount_paid_against, paid_date, broken_reason_agent_coded, agent_id
                              FROM promises_to_pay WHERE case_id IN ({ph}) ORDER BY ptp_created_ts""", ids)
    rec["contacts"] = w.q(f"""SELECT contact_id, case_id, agent_id, contact_ts_local AS ts, coalesce(channel_v2, channel) AS channel,
                                     direction, outcome_desc, system_event_type, sms_text, ptp_made_flag, payment_amount, rpc_flag,
                                     transcript_id, hardship_mentioned_flag, vulnerability_disclosed_flag, dispute_raised_flag,
                                     complaint_raised_flag, cease_request_flag
                              FROM contact_history WHERE case_id IN ({ph}) ORDER BY contact_ts_local DESC LIMIT 200""", ids)
    rec["calls"] = w.q(f"""SELECT t.transcript_id, t.contact_id, t.case_id, t.agent_id, t.call_start_ts, t.duration_sec, t.direction,
                                  t.language, v.voice_sample_id, nullif(f.hardship_signal, 'none') AS hardship_signal, f.hardship_reason, f.dispute_signal, f.cease_request, f.next_step
                           FROM call_transcripts t LEFT JOIN voice_samples v ON v.contact_id = t.contact_id
                           LEFT JOIN features.transcript_features f ON f.transcript_id = t.transcript_id
                           WHERE t.case_id IN ({ph}) ORDER BY t.call_start_ts""", ids)
    return rec


def _ops_customer(g: str, case_ids: list[str], contact_ids: list[str]) -> dict[str, list[dict]]:
    cph = ",".join("?" * len(case_ids))
    out = {
        "flags": _ops("SELECT event_id, ts, from_level, to_level, source, reviewer_id, reason, program_id, audit_id FROM hardship_flag_events WHERE golden_id = ? ORDER BY event_id", (g,)),
        "decisions": _ops(f"SELECT decision_id, ts, case_id, decision, final_json, reason_code, note, user_id, audit_id FROM nba_decisions WHERE golden_id = ? OR case_id IN ({cph}) ORDER BY decision_id", (g, *case_ids)),
        "sims": _ops(f"SELECT run_id, ts, case_id, user_id, levers_json, result_json, chosen FROM simulator_runs WHERE case_id IN ({cph}) ORDER BY run_id", tuple(case_ids)),
        "summaries": [],
    }
    if contact_ids:
        ph = ",".join("?" * len(contact_ids))
        out["summaries"] = _ops(f"SELECT contact_id, status, approved_by, approved_ts FROM call_summaries WHERE contact_id IN ({ph})", tuple(contact_ids))
    return out


def _contact_text(r: dict) -> str:
    sys_evt = (r.get("system_event_type") or "").replace("_", " ")
    bits = [sys_evt.capitalize() if sys_evt else (r.get("outcome_desc") or "")]
    if r.get("sms_text"):
        bits.append(f"“{r['sms_text'][:90]}”")
    if r.get("ptp_made_flag"):
        bits.append("promise to pay taken")
    if r.get("payment_amount"):
        bits.append(f"payment ${float(r['payment_amount']):,.2f}")
    for flag, text in (("hardship_mentioned_flag", "hardship mentioned"), ("vulnerability_disclosed_flag", "vulnerability disclosed"),
                       ("dispute_raised_flag", "dispute raised"), ("complaint_raised_flag", "complaint raised"), ("cease_request_flag", "asked to stop contact")):
        if r.get(flag):
            bits.append(text)
    return "; ".join(b for b in bits if b) or (r.get("direction") or "")


def _recent(v: Any, days: int = RECENT_DAYS) -> bool:
    d = _day(v)
    return bool(d) and dt.date.fromisoformat(d) >= _as_of() - dt.timedelta(days=days)


# ------------------------------------------------------------------ agent: one customer, everything over time
def _agent_customer(s: Session, g: str) -> TrackView:
    from api.services.hardship import current_level

    with _W() as w:
        rec = _customer_records(w, g)
        accounts = w.q("""SELECT source_system, account_id, product_type, open_date, account_status, current_balance, past_due_amount, dpd, is_open
                          FROM c360_account WHERE golden_id = ? ORDER BY open_date""", [g])
        notes = w.q(f"""SELECT note_id, contact_id, case_id, agent_id, note_ts, note_type, note_text FROM agent_notes
                        WHERE case_id IN ({rec['ph']}) ORDER BY note_ts DESC LIMIT 80""", rec["case_ids"])
    c, cases, promises, contacts, calls = rec["customer"], rec["cases"], rec["promises"], rec["contacts"], rec["calls"]
    opsd = _ops_customer(g, rec["case_ids"], [x["contact_id"] for x in calls])
    summaries = {x["contact_id"]: x for x in opsd["summaries"]}
    level = current_level(g)
    mine = [k for k in cases if k["assigned_agent_id"] == s.user_id]
    open_case = next((k for k in mine if k["case_status"] == "open"), None) or next((k for k in cases if k["case_id"] == c["open_case_id"]), None)

    ev: list[Event] = []
    for a in accounts:
        if a["open_date"]:
            ev.append(Event(ts=_iso(a["open_date"]), type="account", title=f"{PRODUCT_LABEL.get(a['product_type'], a['product_type'])} opened",
                            detail=f"{SYSTEM_LABEL.get(a['source_system'], a['source_system'])} account ••{str(a['account_id'])[-4:]}; now {a['account_status']}, {a['dpd'] or 0} days past due",
                            ref=a["account_id"], table="gold.c360_account"))
    for k in cases:
        ev.append(Event(ts=_iso(k["case_open_date"]), type="case", title=f"Collections case opened ({CASE_PRODUCT_LABEL.get(k['primary_product'], k['primary_product'])})",
                        detail=f"{k['entry_dpd']} days past due at entry; strategy {k['strategy_code']}; assigned to {k['assigned_agent_id'] or 'no one'}",
                        ref=k["case_id"], table="silver.collections_cases", tone="warn" if k["hardship_flag"] else "info"))
        if k["hardship_flag"]:
            ev.append(Event(ts=_iso(k["case_open_date"]), type="hardship", title="Case flagged hardship",
                            detail=" · ".join(x for x in [k["hardship_source"] and f"source {k['hardship_source']}", k["hardship_reason"]] if x),
                            ref=k["case_id"], table="silver.collections_cases", tone="care"))
        if k["cure_flag"] and k["cure_date"]:
            ev.append(Event(ts=_iso(k["cure_date"]), type="case", title="Case cured", detail="Back to current", ref=k["case_id"], table="silver.collections_cases", tone="good"))
        elif k["case_status"] != "open" and k["case_status_date"]:
            ev.append(Event(ts=_iso(k["case_status_date"]), type="case", title=f"Case {k['case_status']}", detail=k["outcome"], ref=k["case_id"], table="silver.collections_cases"))
        if k["human_override_flag"]:
            ev.append(Event(ts=_iso(k["case_status_date"] or k["case_open_date"]), type="nba", title="Recommendation overridden (bank record)",
                            detail=k["override_reason"], ref=k["case_id"], table="silver.collections_cases", tone="warn"))
    for p in promises:
        ev.append(Event(ts=_iso(p["ptp_created_ts"]), type="promise", title=f"Promise to pay {_cad(p['ptp_amount'])} by {_day(p['ptp_due_date'])}",
                        detail=f"Taken by {p['agent_id'] or 'self-serve'}", ref=p["ptp_id"], table="silver.promises_to_pay"))
        if p["ptp_status"] in ("kept", "partially_kept", "broken") and p["status_ts"]:
            tone = "good" if p["ptp_status"] == "kept" else ("warn" if p["ptp_status"] == "broken" else "info")
            ev.append(Event(ts=_iso(p["status_ts"]), type="promise", title=f"Promise {p['ptp_status'].replace('_', ' ')}",
                            detail=f"Paid {_cad(p['amount_paid_against'])} of {_cad(p['ptp_amount'])}" + (f"; reason: {p['broken_reason_agent_coded']}" if p["broken_reason_agent_coded"] else ""),
                            ref=p["ptp_id"], table="silver.promises_to_pay", tone=tone))
    call_ids = {x["contact_id"] for x in calls}
    for r in contacts:
        if r["contact_id"] in call_ids:
            continue  # shown once, as a call with its transcript
        ev.append(Event(ts=_iso(r["ts"]), type="contact", title=f"{CHANNEL_LABEL.get(r['channel'] or 'system', (r['channel'] or 'contact').capitalize())} {r['direction'] or ''}".strip(),
                        detail=_contact_text(r), ref=r["contact_id"], table="silver.contact_history",
                        tone="care" if r["hardship_mentioned_flag"] or r["vulnerability_disclosed_flag"] else ("warn" if "broken" in (r["system_event_type"] or "") else "info")))
    for t in calls:
        sm = summaries.get(t["contact_id"])
        bits = [f"{int(t['duration_sec'] or 0) // 60} min {t['direction']} call in {t['language']}"]
        if t["hardship_signal"]:
            bits.append(f"hardship signal {t['hardship_signal']} ({t['hardship_reason'] or 'unspecified'})")
        if t["next_step"]:
            bits.append(f"next step: {t['next_step']}")
        bits.append(f"summary {sm['status']}" if sm else "summary not yet approved")
        ev.append(Event(ts=_iso(t["call_start_ts"]), type="call", title="Call with transcript", detail="; ".join(bits),
                        ref=t["contact_id"], table="silver.call_transcripts", link=f"/calls/{t['contact_id']}",
                        tone="care" if t["hardship_signal"] else "info"))
        if t["voice_sample_id"]:
            ev.append(Event(ts=_iso(t["call_start_ts"]), type="recording", title="Call recording available",
                            detail="Play it on the call page (call-level measures only).", ref=t["contact_id"],
                            table="silver.voice_samples", link=f"/calls/{t['contact_id']}"))
    for n in notes:
        ev.append(Event(ts=_iso(n["note_ts"]), type="note", title=f"Agent note ({(n['note_type'] or 'note').replace('_', ' ')})",
                        detail=(n["note_text"] or "")[:180], ref=n["note_id"], table="silver.agent_notes"))
    for f in opsd["flags"]:
        ev.append(Event(ts=_iso(f["ts"]), type="hardship", title=f"Hardship flag {f['from_level']} to {f['to_level']}",
                        detail=" · ".join(x for x in [f"by {f['reviewer_id'] or f['source']}", f["reason"], f["program_id"] and f"program {f['program_id']}"] if x),
                        ref=str(f["audit_id"]), table="ops.hardship_flag_events", tone="care"))
    for d in opsd["decisions"]:
        final = json.loads(d["final_json"] or "{}")
        ev.append(Event(ts=_iso(d["ts"]), type="nba", title=f"Next best action {('approved' if d['decision'] == 'approve' else d['decision'] + 'd').replace('editd', 'edited')}",
                        detail=" · ".join(x for x in [final.get("treatment", "").replace("_", " "), final.get("channel"), d["reason_code"] and f"reason {d['reason_code']}", d["note"], f"by {d['user_id']}"] if x),
                        ref=str(d["audit_id"]), table="ops.nba_decisions", tone="warn" if d["decision"] == "override" else "good"))
    for x in opsd["summaries"]:
        if x["status"] == "approved" and x["approved_ts"]:
            ev.append(Event(ts=_iso(x["approved_ts"]), type="summary", title="Post-call summary approved", detail=f"by {x['approved_by']}",
                            ref=x["contact_id"], table="ops.call_summaries", link=f"/calls/{x['contact_id']}", tone="good"))
    ev.sort(key=lambda e: e.ts, reverse=True)

    ins = _agent_insights(c, cases, open_case, promises, contacts, calls, summaries, level, rec["ph"])
    pending = [t for t in calls if summaries.get(t["contact_id"], {}).get("status") != "approved"][-5:][::-1]
    actions: list[Action] = []
    if open_case and open_case["assigned_agent_id"] == s.user_id:
        actions.append(Action(id="nba", kind="nba", label="Next best action", target=open_case["case_id"],
                              endpoint=f"/nba/{open_case['case_id']}/decision",
                              detail="Approve, change or override. Every decision is written to the audit log."))
    elif open_case:
        actions.append(Action(id="nba", kind="nba", label="Next best action", target=open_case["case_id"], enabled=False,
                              why_disabled="The open case is assigned to another agent, so its next best action is theirs."))
    for t in pending:
        actions.append(Action(id=f"summary-{t['contact_id']}", kind="summary", label=f"Review the summary of the call on {_day(t['call_start_ts'])}",
                              link=f"/calls/{t['contact_id']}", endpoint=f"/calls/{t['contact_id']}/summary/approve", target=t["contact_id"],
                              detail="Check the draft against the transcript, edit, then approve. Only approved values are saved."))
    actions.append(Action(id="c360", kind="link", label="Open the full customer page", link=f"/customers/{g}"))

    kept = sum(p["ptp_status"] == "kept" for p in promises)
    broken = sum(p["ptp_status"] == "broken" for p in promises)
    promise_rows = [[p["ptp_id"], _day(p["ptp_created_ts"]), _day(p["ptp_due_date"]), float(p["ptp_amount"] or 0), p["ptp_status"].replace("_", " "),
                     float(p["amount_paid_against"] or 0), p["broken_reason_agent_coded"]] for p in promises[::-1]]
    call_rows = [[_day(t["call_start_ts"]), t["contact_id"], f"{int(t['duration_sec'] or 0) // 60} min", "yes" if t["voice_sample_id"] else "no",
                  "yes" if t["hardship_signal"] else "no", summaries.get(t["contact_id"], {}).get("status", "not approved")] for t in calls[::-1]]
    acct_rows = [[PRODUCT_LABEL.get(a["product_type"], a["product_type"]), "••" + str(a["account_id"])[-4:], SYSTEM_LABEL.get(a["source_system"], a["source_system"]),
                  _day(a["open_date"]), a["account_status"], float(a["current_balance"] or 0), float(a["past_due_amount"] or 0), a["dpd"]] for a in accounts]
    ph = rec["ph"]
    return TrackView(
        meta=_meta(), kind="customer", id=g, title=c["display_name"], golden_id=g, case_id=open_case["case_id"] if open_case else None,
        subtitle=" · ".join(x for x in [g, ", ".join(y for y in [c["city"], c["province_code"]] if y), (c["segment"] or "").replace("_", " ")] if x),
        badges=[b for b in [level != "none" and f"Hardship {level}", c["vulnerability_flag"] and "Vulnerable", c["dispute_open_flag"] and "Open dispute",
                            c["contact_block"] not in (None, "none") and f"Contact blocked: {c['contact_block']}"] if b],
        figures=[Fact(label="Past due", value=_cad(c["total_past_due_cad"])), Fact(label="Days past due", value=str(c["max_dpd"] or 0)),
                 Fact(label="Promises kept", value=f"{kept} of {kept + broken}" if kept + broken else "none yet"),
                 Fact(label="Open case", value=open_case["case_id"] if open_case else "none")],
        insights=ins,
        sections=[
            Section(id="timeline", label="Timeline", kind="timeline", events=ev[:400],
                    intro="Everything on record for this customer, newest first: accounts, cases, promises, contacts, notes, calls, recordings, hardship flags, decisions and summaries."),
            Section(id="promises", label="Promises", kind="table", tables=[Table(columns=["Promise", "Made", "Due", "Amount", "Status", "Paid", "Reason (agent coded)"], rows=promise_rows,
                    source=_sql_src("Promises on this customer's cases", f"SELECT ptp_id, ptp_created_ts, ptp_due_date, ptp_amount, ptp_status, amount_paid_against, broken_reason_agent_coded FROM silver.promises_to_pay WHERE case_id IN (SELECT case_id FROM gold.c360_case WHERE golden_id = '{g}')"))]),
            Section(id="calls", label="Calls", kind="table", intro="Open a call to read the transcript, play the recording and approve the post-call summary.",
                    tables=[Table(columns=["Date", "Call", "Length", "Recording", "Hardship signal", "Summary"], rows=call_rows,
                                  source=_sql_src("Calls on this customer's cases", f"SELECT t.contact_id, t.call_start_ts, t.duration_sec, v.voice_sample_id, f.hardship_signal FROM silver.call_transcripts t LEFT JOIN silver.voice_samples v USING (contact_id) LEFT JOIN features.transcript_features f USING (transcript_id) WHERE t.case_id IN ({ph})"))]),
            Section(id="accounts", label="Accounts", kind="table", tables=[Table(columns=["Product", "Account", "System", "Opened", "Status", "Balance", "Past due", "Days past due"], rows=acct_rows,
                    source=_sql_src("Accounts linked to this golden ID", f"SELECT product_type, account_id, source_system, open_date, account_status, current_balance, past_due_amount, dpd FROM gold.c360_account WHERE golden_id = '{g}'"))]),
        ],
        actions=actions,
    )


def _agent_insights(c, cases, open_case, promises, contacts, calls, summaries, level, ph) -> list[Insight]:
    out: list[Insight] = []
    g = c["golden_id"]
    recent_p = [p for p in promises if p["ptp_status"] in ("kept", "broken", "partially_kept") and _recent(p["status_ts"])]
    if recent_p:
        br = [p for p in recent_p if p["ptp_status"] == "broken"]
        kp = [p for p in recent_p if p["ptp_status"] == "kept"]
        out.append(Insight(id="promises", title=f"{len(br)} broken, {len(kp)} kept in the last {RECENT_DAYS} days",
                           reason=("A promise broke recently, so a gentler or better-timed promise may work better." if br else "Recent promises were kept."),
                           tone="warn" if br else "good", source=_rec_src("Promises resolved in the last 30 days", "silver.promises_to_pay", [p["ptp_id"] for p in recent_p])))
    if open_case:
        e, n = open_case["entry_dpd"], open_case["current_dpd"]
        if e is not None and n is not None:
            out.append(Insight(id="dpd", title=f"Days past due went from {e} to {n}",
                               reason=f"Since the case opened on {_day(open_case['case_open_date'])}, the arrears {'grew' if n > e else 'shrank' if n < e else 'stayed the same'}. Payments since opening: {_cad(open_case['payments_since_open_amount'])} in {open_case['payments_since_open_count'] or 0} payments.",
                               tone="warn" if n > e else "good" if n < e else "info",
                               source=_rec_src("The open case", "silver.collections_cases", [open_case["case_id"]])))
        if open_case["contact_cap_7d"]:
            used, cap = open_case["contacts_last_7d"] or 0, open_case["contact_cap_7d"]
            out.append(Insight(id="cap", title=f"{used} of {cap} contacts used in the last 7 days",
                               reason="The contact cap is part of the policy gate: once it is reached, no more contacts are proposed this week." if used >= cap else "There is room under the weekly contact cap.",
                               tone="warn" if used >= cap else "info", source=_rec_src("Contact cap on the open case", "silver.collections_cases", [open_case["case_id"]])))
        if open_case["current_ptp_id"]:
            out.append(Insight(id="open_ptp", title=f"Open promise: {_cad(open_case['current_ptp_amount'])} due {_day(open_case['current_ptp_due_date'])}",
                               reason="Check the date against payday in the Promise tab of the customer page before changing it.",
                               source=_rec_src("Current promise on the case", "silver.promises_to_pay", [open_case["current_ptp_id"]])))
    hard = [r for r in contacts if (r["hardship_mentioned_flag"] or r["vulnerability_disclosed_flag"]) and _recent(r["ts"], 60)]
    hard_calls = [t for t in calls if t["hardship_signal"] and _recent(t["call_start_ts"], 60)]
    if hard or hard_calls or level != "none":
        ids = [r["contact_id"] for r in hard] + [t["contact_id"] for t in hard_calls]
        out.append(Insight(id="hardship", title=f"Hardship is {level}" + (f"; {len(ids)} signal(s) in the last 60 days" if ids else ""),
                           reason="When hardship is possible or confirmed, pressure actions stop and support options come first (the hardship latch). Only a hardship specialist can lower it, with a reason.",
                           tone="care", source=_rec_src("Contacts and calls with a hardship signal", "silver.contact_history", ids) if ids
                           else _sql_src("Current hardship level", f"SELECT to_level FROM hardship_flag_events WHERE golden_id = '{g}' ORDER BY event_id DESC LIMIT 1 -- else gold.c360_customer.hardship_flag")))
    waiting = [t for t in calls if summaries.get(t["contact_id"], {}).get("status") != "approved" and _recent(t["call_start_ts"], 60)]
    if waiting:
        out.append(Insight(id="summaries", title=f"{len(waiting)} call summary(ies) from the last 60 days not yet approved",
                           reason="Text features from a call feed the next best action only after you approve the summary.",
                           tone="warn", source=_rec_src("Calls without an approved summary", "silver.call_transcripts", [t["contact_id"] for t in waiting])))
    n7 = sum(1 for r in contacts if _recent(r["ts"], 7))
    out.append(Insight(id="contacts", title=f"{n7} contact(s) in the last 7 days, {sum(1 for r in contacts if _recent(r['ts']))} in the last {RECENT_DAYS}",
                       reason="Every contact attempt and system event on this customer's cases, from the contact history.",
                       source=_sql_src("Contacts in the last 30 days", f"SELECT contact_id, contact_ts_local, coalesce(channel_v2, channel) FROM silver.contact_history WHERE case_id IN (SELECT case_id FROM gold.c360_case WHERE golden_id = '{g}') AND contact_ts_local >= DATE '{_as_of() - dt.timedelta(days=RECENT_DAYS)}'")))
    return out


# ------------------------------------------------------------------ hardship specialist: the hardship journey
def _specialist_customer(s: Session, g: str) -> TrackView:
    from api.services.hardship import REVIEW_DAYS, _due, current_level
    from decisioning import eligibility

    with _W() as w:
        rec = _customer_records(w, g)
        offers = w.q(f"""SELECT o.offer_id, o.case_id, o.program_id, p.program_name, o.offer_ts, o.offered_by, o.nba_recommended_flag,
                                o.eligibility_result, o.proposed_payment_amount, o.duration_months, o.customer_response, o.response_ts,
                                o.decline_reason, o.plan_start_date, o.plan_status, o.plan_payments_due, o.plan_payments_made
                         FROM offers o LEFT JOIN (SELECT program_id, any_value(program_name) AS program_name FROM hardship_programs GROUP BY 1) p
                           ON p.program_id = o.program_id
                         WHERE o.case_id IN ({rec['ph']}) ORDER BY o.offer_ts""", rec["case_ids"])
        note_sig = w.q(f"""SELECT n.note_id, n.contact_id, n.case_id, n.available_ts, n.hardship_signal, n.hardship_reason
                           FROM features.note_features n WHERE n.case_id IN ({rec['ph']}) AND n.hardship_signal <> 'none' ORDER BY n.available_ts""", rec["case_ids"])
    c, cases, contacts, calls = rec["customer"], rec["cases"], rec["contacts"], rec["calls"]
    opsd = _ops_customer(g, rec["case_ids"], [])
    level = current_level(g)
    open_case = next((k for k in cases if k["case_id"] == c["open_case_id"]), None)
    ev: list[Event] = []
    for r in contacts:
        if r["hardship_mentioned_flag"] or r["vulnerability_disclosed_flag"]:
            ev.append(Event(ts=_iso(r["ts"]), type="signal", title=f"Signal in a {r['channel'] or 'contact'}: " + ("hardship mentioned" if r["hardship_mentioned_flag"] else "vulnerability disclosed"),
                            detail=_contact_text(r), ref=r["contact_id"], table="silver.contact_history", tone="care"))
    for t in calls:
        if t["hardship_signal"]:
            ev.append(Event(ts=_iso(t["call_start_ts"]), type="signal", title="Signal in a call transcript" + (" (recording available)" if t["voice_sample_id"] else ""),
                            detail=f"Level {t['hardship_signal']}; reason: {t['hardship_reason'] or 'unspecified'}" + (f"; next step: {t['next_step']}" if t["next_step"] else ""),
                            ref=t["contact_id"], table="features.transcript_features", tone="care"))
        if t["voice_sample_id"]:
            ev.append(Event(ts=_iso(t["call_start_ts"]), type="recording", title="Call recording", detail="Play it here (call-level measures only, never voice traits).",
                            ref=t["contact_id"], table="silver.voice_samples"))
    for n in note_sig:
        ev.append(Event(ts=_iso(n["available_ts"]), type="signal", title="Signal in an agent note", detail=f"Level {n['hardship_signal']}; reason: {n['hardship_reason'] or 'unspecified'}",
                        ref=n["note_id"], table="features.note_features", tone="care"))
    for k in cases:
        if k["hardship_flag"]:
            ev.append(Event(ts=_iso(k["case_open_date"]), type="hardship", title="Case flagged hardship",
                            detail=" · ".join(x for x in [k["hardship_source"] and f"source {k['hardship_source']}", k["hardship_reason"]] if x),
                            ref=k["case_id"], table="silver.collections_cases", tone="care"))
    for f in opsd["flags"]:
        ev.append(Event(ts=_iso(f["ts"]), type="hardship", title=f"Flag {f['from_level']} to {f['to_level']}",
                        detail=" · ".join(x for x in [f"by {f['reviewer_id'] or f['source']}", f["reason"], f["program_id"] and f"program {f['program_id']}"] if x),
                        ref=str(f["audit_id"]), table="ops.hardship_flag_events", tone="care"))
    for o in offers:
        ev.append(Event(ts=_iso(o["offer_ts"]), type="offer", title=f"Offered {o['program_name'] or o['program_id']}",
                        detail=" · ".join(x for x in [f"by {o['offered_by']}", o["eligibility_result"] and o["eligibility_result"].replace("_", " "), o["customer_response"] and f"customer {o['customer_response']}", o["decline_reason"] and f"reason: {o['decline_reason']}"] if x),
                        ref=o["offer_id"], table="silver.offers", tone="warn" if o["customer_response"] == "declined" else "info"))
        if o["plan_start_date"]:
            ev.append(Event(ts=_iso(o["plan_start_date"]), type="plan", title=f"Plan started ({o['program_name'] or o['program_id']})",
                            detail=f"{o['plan_payments_made'] or 0} of {o['plan_payments_due'] or 0} payments made; status {o['plan_status'] or 'n/a'}",
                            ref=o["offer_id"], table="silver.offers", tone="warn" if o["plan_status"] == "broken" else "good"))
    for r in opsd["sims"]:
        lv = json.loads(r["levers_json"] or "{}")
        ev.append(Event(ts=_iso(r["ts"]), type="simulation", title="Plan simulated", detail=", ".join(f"{k} {v}" for k, v in lv.items() if v not in (None, False, ""))[:180],
                        ref=str(r["run_id"]), table="ops.simulator_runs"))
    ev.sort(key=lambda e: e.ts, reverse=True)

    elig = eligibility.check(open_case["case_id"]) if open_case else None
    progs = (elig or {}).get("programs", [])
    eligible = [p for p in progs if p.get("eligible")]
    elig_rows = [[p["program_id"], p.get("program_name"), "yes" if p.get("eligible") else "no", p.get("approver_level"),
                  "; ".join(f"{r['rule'].replace('_', ' ')} ({r['value']} vs {r['limit']})" for r in p.get("rules", []) if not r.get("passed")) or "all rules pass"] for p in progs]
    offer_rows = [[_day(o["offer_ts"]), o["program_name"] or o["program_id"], o["offered_by"], (o["eligibility_result"] or "").replace("_", " "),
                   o["customer_response"], o["decline_reason"], _day(o["plan_start_date"]) or None, o["plan_status"]] for o in offers[::-1]]
    plans = [o for o in offers if o["plan_start_date"]]
    plan_rows = [[_day(o["plan_start_date"]), o["program_name"] or o["program_id"], o["plan_payments_made"] or 0, o["plan_payments_due"] or 0,
                  _pct((o["plan_payments_made"] or 0) / o["plan_payments_due"]) if o["plan_payments_due"] else "n/a", o["plan_status"]] for o in plans]
    sim_rows = []
    for r in opsd["sims"][::-1]:
        res = json.loads(r["result_json"] or "{}").get("results") or {}
        sim_rows.append([_day(r["ts"]), r["case_id"], r["user_id"], ", ".join(f"{k}: {v}" for k, v in json.loads(r["levers_json"] or "{}").items() if v not in (None, False, ""))[:120],
                         ", ".join(f"{k}: {v}" for k, v in list(res.items())[:4]) if isinstance(res, dict) else str(res)[:120]])

    ins: list[Insight] = []
    raised = next((f for f in reversed(opsd["flags"]) if f["to_level"] == "possible"), None)
    raised_day = dt.date.fromisoformat(_day(raised["ts"])) if raised else (open_case["case_open_date"] if open_case and open_case["hardship_flag"] else None)
    if level == "possible" and raised_day:
        due = _due(raised_day)
        ins.append(Insight(id="review", title=f"Review due {due}" + (" (overdue)" if due < _as_of() else ""),
                           reason=f"A possible flag must be confirmed or cleared by a person within {REVIEW_DAYS} business days; it stays fail-safe (no pressure) until then.",
                           tone="warn" if due < _as_of() else "care",
                           source=_rec_src("When the flag was raised", "ops.hardship_flag_events" if raised else "silver.collections_cases", [raised["audit_id"] if raised else open_case["case_id"]])))
    sigs = [e for e in ev if e.type == "signal"]
    ins.append(Insight(id="signals", title=f"{len(sigs)} hardship signal(s) on record, {sum(1 for e in sigs if _recent(e.ts, 60))} in the last 60 days",
                       reason="Signals come from contact flags, call transcripts (rules validated on labelled calls) and agent notes. Any one can raise the flag to possible; none can lower it.",
                       tone="care" if sigs else "info", source=_rec_src("Signal records", "silver.contact_history / features.*", [e.ref for e in sigs])))
    declined = [o for o in offers if o["customer_response"] == "declined"]
    if offers:
        ins.append(Insight(id="offers", title=f"{len(offers)} offer(s) made, {len(declined)} declined",
                           reason=("Decline reasons: " + ", ".join(sorted({o['decline_reason'] for o in declined if o['decline_reason']})) + ".") if declined else "No offer was declined.",
                           tone="warn" if declined else "info", source=_rec_src("Offers", "silver.offers", [o["offer_id"] for o in offers])))
    if open_case:
        missed = level in ("possible", "clear") and not offers and any(p.get("approver_level") == "agent" for p in eligible)
        ins.append(Insight(id="eligible", title=f"Eligible for {len(eligible)} of {len(progs)} program(s)" + ("; none offered yet" if missed else ""),
                           reason="Rules only (product, hardship level, days past due, months on book, uses in 12 months, insolvency, broken plan in 90 days). A language model never decides eligibility.",
                           tone="warn" if missed else "info", source=_rec_src("Eligibility rules on the open case", "silver.hardship_programs", [open_case["case_id"]])))
    broken_plans = [o for o in plans if o["plan_status"] == "broken"]
    if plans:
        ins.append(Insight(id="plans", title=f"{len(plans)} plan(s), {len(broken_plans)} broken",
                           reason="Plan survival is payments made against payments due. A broken plan in the last 90 days rules out some programs.",
                           tone="warn" if broken_plans else "good", source=_rec_src("Plans", "silver.offers", [o["offer_id"] for o in plans])))

    actions: list[Action] = []
    opts = [Fact(label=f"{p['program_id']}: {p.get('program_name') or ''}".strip(), value=p["program_id"]) for p in eligible]
    actions.append(Action(id="confirm", kind="hardship_confirm", label="Confirm hardship and link a program", endpoint=f"/hardship/{g}/flag", target=g, options=opts,
                          enabled=bool(opts) and level != "clear",
                          why_disabled="Hardship is already confirmed." if level == "clear" else (None if opts else "No program fits this case right now."),
                          detail="Sets the flag to confirmed with the program you choose. Written to the audit log and the flag history."))
    actions.append(Action(id="lower", kind="hardship_lower", label="Lower the flag (with a reason)", endpoint=f"/hardship/{g}/flag", target=g,
                          enabled=level != "none", why_disabled="The flag is already none." if level == "none" else None,
                          options=[Fact(label="To possible", value="possible"), Fact(label="To none", value="none")] if level == "clear" else [Fact(label="To none", value="none")],
                          detail="Only a person can lower the hardship latch, and a reason is required. It is written to the flag history and the audit log."))
    if open_case:
        actions.append(Action(id="simulator", kind="simulator", label="Open the plan simulator", link=f"/hardship/simulator/{open_case['case_id']}", target=open_case["case_id"],
                              detail="Try plan levers within policy limits. Every run is logged."))
    case_ph = rec["ph"]
    return TrackView(
        meta=_meta(), kind="customer", id=g, title=_short(c["display_name"]), golden_id=g, case_id=open_case["case_id"] if open_case else None,
        subtitle=" · ".join(x for x in [g, c["province_code"], open_case and f"open case {open_case['case_id']}"] if x),
        badges=[b for b in [f"Hardship {level}", c["vulnerability_flag"] and "Vulnerable"] if b],
        figures=[Fact(label="Hardship level", value=level), Fact(label="Signals", value=str(len(sigs))), Fact(label="Offers", value=str(len(offers))),
                 Fact(label="Eligible programs", value=str(len(eligible)))],
        insights=ins,
        sections=[
            Section(id="journey", label="Hardship journey", kind="timeline", events=ev,
                    intro="Signals, flag changes, offers, plans and simulations, newest first. Recordings play here; only call-level measures are shown."),
            Section(id="eligibility", label="Eligibility", kind="table", tables=[Table(columns=["Program", "Name", "Eligible", "Approver", "Rules that fail"], rows=elig_rows,
                    note="Rules only. Income evidence, where a program needs it, does not fail the check: ask for it.",
                    source=_rec_src("decisioning.eligibility.check on the open case", "silver.hardship_programs", [open_case["case_id"]] if open_case else []))]),
            Section(id="offers", label="Offers", kind="table", tables=[Table(columns=["Offered", "Program", "By", "Eligibility", "Response", "Decline reason", "Plan start", "Plan status"], rows=offer_rows,
                    source=_sql_src("Offers on this customer's cases", f"SELECT offer_ts, program_id, offered_by, eligibility_result, customer_response, decline_reason, plan_start_date, plan_status FROM silver.offers WHERE case_id IN ({case_ph})"))]),
            Section(id="plans", label="Plans", kind="table", intro="Plan survival: payments made against payments due, and simulated plans.",
                    tables=[Table(title="Plan survival", columns=["Started", "Program", "Payments made", "Payments due", "Survival", "Status"], rows=plan_rows,
                                  source=_sql_src("Plans", f"SELECT plan_start_date, program_id, plan_payments_made, plan_payments_due, plan_status FROM silver.offers WHERE case_id IN ({case_ph}) AND plan_start_date IS NOT NULL")),
                            Table(title="Simulated plans", columns=["Date", "Case", "By", "Levers", "Results"], rows=sim_rows,
                                  source=Source(kind="records", label="Simulator runs (ops store)", table="ops.simulator_runs", ids=[str(r["run_id"]) for r in opsd["sims"]]))]),
        ],
        actions=actions,
    )


# ------------------------------------------------------------------ team lead: an agent on the team
def _lead_agent(s: Session, agent_id: str) -> TrackView:
    months = _months_back(12)
    start = months[0] + "-01"
    kept_sql = f"""SELECT strftime(date_trunc('month', p.ptp_due_date), '%Y-%m') AS month,
                          round(100.0 * avg(CASE WHEN p.ptp_status = 'kept' THEN 1 ELSE 0 END), 1) AS promise_kept_rate_pct, count(*) AS promises
                   FROM promises_to_pay p WHERE p.agent_id = '{agent_id}' AND p.ptp_status IN ('kept', 'partially_kept', 'broken')
                     AND p.ptp_due_date >= DATE '{start}' AND p.ptp_due_date <= DATE '{_as_of()}' GROUP BY 1 ORDER BY 1"""
    contacts_sql = f"""SELECT strftime(date_trunc('month', h.contact_ts_local), '%Y-%m') AS month, count(*) AS contacts,
                              count(*) FILTER (WHERE h.rpc_flag) AS rpcs,
                              count(*) FILTER (WHERE coalesce(h.channel_v2, h.channel) = 'call' AND NOT h.within_permitted_hours_flag) AS out_of_hours_calls
                       FROM contact_history h WHERE h.agent_id = '{agent_id}' AND h.contact_ts_local >= TIMESTAMP '{start}' GROUP BY 1 ORDER BY 1"""
    over_sql = f"""SELECT coalesce(override_reason, 'no reason recorded') AS reason, count(*) AS cases FROM collections_cases
                   WHERE assigned_agent_id = '{agent_id}' AND human_override_flag GROUP BY 1 ORDER BY 2 DESC"""
    guard_sql = f"""SELECT count(*) FILTER (WHERE case_status = 'open') AS open_cases, count(*) AS all_cases,
                           coalesce(sum(contact_cap_breach_count), 0) AS cap_breaches, coalesce(sum(out_of_hours_contact_count), 0) AS out_of_hours,
                           count(*) FILTER (WHERE human_override_flag) AS overrides, count(*) FILTER (WHERE case_status = 'open' AND hardship_flag) AS open_hardship
                    FROM collections_cases WHERE assigned_agent_id = '{agent_id}'"""
    with _W() as w:
        a = w.q("""SELECT agent_id, agent_display_name, site, team_id, role, tenure_months, current_case_load, max_concurrent_cases,
                          ptp_kept_rate_90d, cure_rate_90d, rpc_rate_90d, qa_score_avg_90d, complaints_90d, skill_hardship, vulnerable_customer_certified
                   FROM agents WHERE agent_id = ?""", [agent_id])[0]
        kept = {r["month"]: r for r in w.q(kept_sql)}
        cont = {r["month"]: r for r in w.q(contacts_sql)}
        overrides = w.q(over_sql)
        guard = w.q(guard_sql)[0]
    ops_over = _ops("SELECT coalesce(reason_code, 'none') AS reason, count(*) AS n FROM nba_decisions WHERE user_id = ? AND decision = 'override' GROUP BY 1 ORDER BY 2 DESC", (agent_id,))
    ops_dec = _ops("SELECT decision, count(*) AS n FROM nba_decisions WHERE user_id = ? GROUP BY 1", (agent_id,))
    from decisioning.assistant import data

    q = data.queue_df()
    queue_today = 0 if q is None else int(((q.assigned_agent_id == agent_id) & (q.status == "scheduled")).sum())
    kept_vals = [kept[m]["promise_kept_rate_pct"] / 100 if m in kept else None for m in months]
    kept_n = [kept[m]["promises"] if m in kept else 0 for m in months]
    ins: list[Insight] = []
    last3 = [kept[m] for m in months[-3:] if m in kept]
    prev3 = [kept[m] for m in months[-6:-3] if m in kept]

    def rate(rows):
        n = sum(r["promises"] for r in rows)
        return (sum(r["promise_kept_rate_pct"] * r["promises"] for r in rows) / n / 100, n) if n else (None, 0)

    r3, n3 = rate(last3)
    p3, np3 = rate(prev3)
    if r3 is not None:
        diff = None if p3 is None else r3 - p3
        ins.append(Insight(id="kept", title=f"Promises kept: {_pct(r3)} over the last 3 months" + (f" ({'+' if diff >= 0 else ''}{diff * 100:.0f} pts)" if diff is not None else ""),
                           reason=f"{n3} resolved promises in the last 3 months against {np3} in the 3 before." + (" Few promises: read the trend with care." if n3 < 30 else ""),
                           tone="good" if diff is not None and diff > 0.02 else "warn" if diff is not None and diff < -0.02 else "info", source=_sql_src("Promise kept rate by month", kept_sql)))
    top = overrides[0] if overrides else None
    ins.append(Insight(id="overrides", title=f"{guard['overrides']} case(s) overridden" + (f"; most often: {top['reason']}" if top else ""),
                       reason="Overrides are allowed with a reason code; a pattern of the same reason is worth a coaching chat or a rule review." + (f" In this app: {sum(o['n'] for o in ops_over)} override(s) recorded." if ops_over else ""),
                       tone="info", source=_sql_src("Overrides by reason", over_sql)))
    breaches = int(guard["cap_breaches"]) + int(guard["out_of_hours"])
    ins.append(Insight(id="guardrails", title=f"{guard['cap_breaches']} contact-cap breach(es), {guard['out_of_hours']} out-of-hours contact(s)",
                       reason="Both must be zero under the contact rules; any breach is reviewed." if breaches else "No guardrail breach on this agent's cases.",
                       tone="warn" if breaches else "good", source=_sql_src("Guardrail counts on the agent's cases", guard_sql)))
    load, cap = a["current_case_load"] or 0, a["max_concurrent_cases"] or 0
    ins.append(Insight(id="queue", title=f"Case load {load} of {cap}; {queue_today} action(s) scheduled today",
                       reason="Near the maximum, new cases should go to someone else (reassign from the team page)." if cap and load >= 0.9 * cap else "There is capacity for new cases.",
                       tone="warn" if cap and load >= 0.9 * cap else "info",
                       source=Source(kind="records", label="silver.agents and today's NBA queue", table="silver.agents", ids=[agent_id])))
    actions = _lead_actions(s)
    actions.insert(0, Action(id="queue", kind="link", label="Open the team's queue", link="/queue", detail="Today's actions for your team; filter by this agent there."))
    actions.insert(1, Action(id="roster", kind="link", label="Open the agent roster (reassign)", link="/team?tab=agents",
                             detail="Reassignment is done in the case management system; the roster shows load and skills."))
    return TrackView(
        meta=_meta(), kind="agent", id=agent_id, title=a["agent_display_name"], subtitle=f"{agent_id} · {a['role'].replace('_', ' ')} · {a['site']} · team {a['team_id']}",
        badges=[b for b in [a["skill_hardship"] and "Hardship-skilled", a["vulnerable_customer_certified"] and "Vulnerable-certified"] if b],
        figures=[Fact(label="Open cases", value=str(guard["open_cases"])), Fact(label="Kept (90 days)", value=_pct(a["ptp_kept_rate_90d"])),
                 Fact(label="Cure (90 days)", value=_pct(a["cure_rate_90d"])), Fact(label="Scheduled today", value=str(queue_today))],
        insights=ins,
        sections=[
            Section(id="promises", label="Promises kept", kind="series", series=[Series(title="Promise kept rate by month due", unit="pct", x=months,
                    lines=[Line(name="Kept rate", values=kept_vals)], note="Months with no resolved promise are blank. " + f"Promises per month: {', '.join(str(n) for n in kept_n[-6:])} (last 6).",
                    source=_sql_src("Promise kept rate by month", kept_sql))]),
            Section(id="contacts", label="Contacts", kind="series", series=[Series(title="Contacts and right-party contacts by month", unit="count", x=months,
                    lines=[Line(name="Contacts", values=[cont[m]["contacts"] if m in cont else 0 for m in months]),
                           Line(name="Right-party contacts", values=[cont[m]["rpcs"] if m in cont else 0 for m in months]),
                           Line(name="Calls outside permitted hours", values=[cont[m]["out_of_hours_calls"] if m in cont else 0 for m in months])],
                    source=_sql_src("Contacts by month", contacts_sql))]),
            Section(id="overrides", label="Overrides", kind="table", tables=[
                Table(title="Overrides on the bank's record", columns=["Reason", "Cases"], rows=[[o["reason"], o["cases"]] for o in overrides], source=_sql_src("Overrides by reason", over_sql)),
                Table(title="Decisions in this app", columns=["Decision or override reason", "Count"],
                      rows=[[d["decision"], d["n"]] for d in ops_dec] + [[f"override: {o['reason']}", o["n"]] for o in ops_over],
                      source=Source(kind="records", label="ops.nba_decisions for this agent", table="ops.nba_decisions", ids=[agent_id]))]),
            Section(id="guardrails", label="Guardrails and queue", kind="facts", facts=[
                Fact(label="Contact-cap breaches", value=str(guard["cap_breaches"])), Fact(label="Out-of-hours contacts", value=str(guard["out_of_hours"])),
                Fact(label="Open hardship cases", value=str(guard["open_hardship"])), Fact(label="Case load", value=f"{load} of {cap}"),
                Fact(label="Scheduled today (NBA queue)", value=str(queue_today)), Fact(label="Right-party contact rate (90 days)", value=_pct(a["rpc_rate_90d"])),
                Fact(label="QA score (90 days)", value=str(a["qa_score_avg_90d"])), Fact(label="Complaints (90 days)", value=str(a["complaints_90d"]))]),
        ],
        actions=actions,
    )


def _lead_actions(s: Session, subject: str | None = None) -> list[Action]:
    """Team-level approvals the lead can do from the tracker, through the existing endpoints."""
    from api.services import nba as nba_svc
    from decisioning import playbooks

    out: list[Action] = []
    try:
        for b in nba_svc.batches("pending", s.team_id)["items"][:6]:
            out.append(Action(id=f"batch-{b['batch_id']}", kind="batch_approve", label=f"Approve {b['count']:,} {b['treatment'].replace('_', ' ')} by {b['channel']}",
                              endpoint=f"/batches/{b['batch_id']}/approve", target=b["batch_id"],
                              detail=f"Check the {b['sample_size']} sampled cases on the Team page first. Audited; nothing is sent from here."))
    except Exception:  # no nightly queue built: no batches to show
        pass
    for p in playbooks.listing(playbooks.PENDING):
        if subject and p["subject_id"] != subject:
            continue
        out.append(Action(id=f"pb-{p['proposal_id']}", kind="playbook_approve", label=p["title"], endpoint=f"/playbooks/{p['proposal_id']}/approve",
                          target=p["proposal_id"], detail=p["detail"]))
        if len(out) > 12:
            break
    return out


# ------------------------------------------------------------------ team lead: an employer from the radar (aggregates)
def _lead_employer(s: Session, key: str) -> TrackView:
    from decisioning import radar

    k = _min_group()
    months = _months_back(12)
    with _W() as w:
        snap = radar._latest_snapshot(w.con)
        size_sql = f"""WITH m AS ({MEMBERS_SQL.replace('= ?', f"= '{key}'")})
            SELECT count(DISTINCT m.golden_id) AS customers,
                   count(DISTINCT k.case_id) FILTER (WHERE k.case_status = 'open') AS open_cases,
                   coalesce(sum(k.total_exposure) FILTER (WHERE k.case_status = 'open'), 0) AS exposure,
                   coalesce(sum(k.total_overdue) FILTER (WHERE k.case_status = 'open'), 0) AS overdue
            FROM m LEFT JOIN c360_case k ON k.golden_id = m.golden_id"""
        pay_sql = f"""WITH m AS ({MEMBERS_SQL.replace('= ?', f"= '{key}'")})
            SELECT s.credit_month AS month, count(DISTINCT m.golden_id) AS customers,
                   count(DISTINCT m.golden_id) FILTER (WHERE s.gap_flag) AS no_payroll
            FROM salary_credit_history s JOIN m ON m.crm_customer_id = s.crm_customer_id
            WHERE s.credit_month >= '{months[0]}' GROUP BY 1 ORDER BY 1"""
        weeks = [(snap - dt.timedelta(days=snap.weekday()) - dt.timedelta(weeks=i)) for i in range(11, -1, -1)] if snap else []
        ei_sql = f"""WITH m AS ({MEMBERS_SQL.replace('= ?', f"= '{key}'")}),
            d AS (SELECT x.golden_id, min(d.ei_first_deposit_date) FILTER (WHERE d.ei_deposit_flag) AS ei_first,
                         max(d.payroll_delay_days) AS delay
                  FROM deposit_accounts d JOIN identity.account_xref x ON x.source_system = 'core_banking' AND x.account_id = d.deposit_account_id
                  WHERE d.snapshot_date = DATE '{snap}' AND x.golden_id IN (SELECT golden_id FROM m) GROUP BY 1)
            SELECT count(*) AS with_deposits, count(*) FILTER (WHERE delay > 7) AS payroll_gap_now,
                   list(strftime(date_trunc('week', ei_first), '%Y-%m-%d')) FILTER (WHERE ei_first >= DATE '{weeks[0] if weeks else snap}') AS ei_weeks
            FROM d"""
        cases_sql = f"""WITH m AS ({MEMBERS_SQL.replace('= ?', f"= '{key}'")})
            SELECT strftime(date_trunc('month', k.case_open_date), '%Y-%m') AS month, count(*) AS cases, count(DISTINCT k.golden_id) AS customers,
                   sum(k.total_exposure) AS exposure
            FROM c360_case k WHERE k.golden_id IN (SELECT golden_id FROM m) AND k.case_open_date >= DATE '{months[0]}-01' GROUP BY 1 ORDER BY 1"""
        size = w.q(size_sql)[0]
        pay = {r["month"]: r for r in w.q(pay_sql)}
        ei = w.q(ei_sql)[0] if snap else {"with_deposits": 0, "payroll_gap_now": 0, "ei_weeks": []}
        cases = {r["month"]: r for r in w.q(cases_sql)}
    if size["customers"] < k:  # checked again on the full member set (the authorisation check counted the same set)
        raise _deny(f"Employers with fewer than {k} customers are hidden (small-group suppression).")
    suppressed = 0
    pay_vals = []
    for m in months:
        r = pay.get(m)
        if not r or r["customers"] < k:
            suppressed += 1 if r else 0
            pay_vals.append(None)
        else:
            pay_vals.append(r["no_payroll"] / r["customers"])
    base = ei["with_deposits"] or 0
    ei_counts = {wk: 0 for wk in [str(x) for x in weeks]}
    for wk in ei["ei_weeks"] or []:
        if wk in ei_counts:
            ei_counts[wk] += 1
    ei_vals = [(n / base if base >= k else None) for n in ei_counts.values()]
    case_vals, case_supp = [], 0
    for m in months:
        r = cases.get(m)
        if r and r["customers"] < k:
            case_supp += 1
            case_vals.append(None)
        else:
            case_vals.append(float(r["cases"]) if r else 0.0)
    row = next((r for r in _radar_rows() if r["employer_key"] == key), None)
    ins: list[Insight] = []
    if row:
        ins.append(Insight(id="radar", title=radar.PATTERN_TEXT.get(row["pattern"], row["pattern"]).split(":")[0],
                           reason=f"This week {row['n_payroll_gap']} of {row['n_customers']} customers have late payroll ({_pct(row.get('gap_rate'))} against {_pct(row.get('peer_gap_rate'))} for industry peers) and {row['n_new_ei']} have new EI deposits. {radar.LABEL}",
                           tone="warn" if row["pattern"] != "none" else "info",
                           source=_sql_src("Employer radar (decisioning.radar.GROUPS_SQL)", radar.GROUPS_SQL.format(ei=radar.NEW_EI_DAYS, gap=radar.GAP_DAYS))))
    shown = [v for v in pay_vals if v is not None]
    if len(shown) >= 2:
        ins.append(Insight(id="payroll", title=f"No payroll credit: {_pct(shown[-1])} in the latest month, {_pct(shown[0])} a year earlier",
                           reason="Share of this employer's customers with no salary credit in the month (salary_credit_history.gap_flag). Months under 10 customers are hidden.",
                           tone="warn" if shown[-1] - shown[0] > 0.05 else "info", source=_sql_src("No-payroll share by month", pay_sql)))
    ins.append(Insight(id="exposure", title=f"{size['open_cases']} open case(s), {_cad(size['exposure'])} exposure",
                       reason="Open collections cases among this employer's customers, summed. Individual customers are not listed here.",
                       source=_sql_src("Customers, open cases and exposure", size_sql)))
    actions = [a for a in _lead_actions(s, subject=key) if a.kind == "playbook_approve"]
    actions.append(Action(id="map", kind="link", label="Open the radar and weather map", link="/map"))
    return TrackView(
        meta=_meta(), kind="employer", id=key, title=f"Employer {key}", aggregates_only=True,
        subtitle=f"Industry {row.get('industry_naics2') if row else 'n/a'} · names are not shown · groups under {k} hidden",
        badges=[row["pattern"].replace("_", " ")] if row and row["pattern"] != "none" else [],
        figures=[Fact(label="Customers", value=str(size["customers"])), Fact(label="Open cases", value=str(size["open_cases"])),
                 Fact(label="Exposure", value=_cad(size["exposure"])), Fact(label="Late payroll now", value=f"{ei['payroll_gap_now']} of {base}" if base >= k else "hidden")],
        insights=ins,
        sections=[
            Section(id="payroll", label="Late payroll", kind="series", series=[Series(title="Share with no payroll credit, by month", unit="pct", x=months,
                    lines=[Line(name="No payroll credit", values=pay_vals)], suppressed=suppressed, note="Months under 10 customers are hidden.", source=_sql_src("No-payroll share by month", pay_sql))]),
            Section(id="ei", label="EI deposits", kind="series", series=[Series(title="New EI deposits, by week first seen", unit="pct", x=[str(x) for x in weeks],
                    lines=[Line(name="Share with a first EI deposit that week", values=ei_vals)], note="Share of customers with a deposit account at this employer; hidden when fewer than 10 have one.",
                    source=_sql_src("EI first deposits by week (latest full deposit snapshot)", ei_sql))]),
            Section(id="cases", label="Open cases", kind="series", series=[Series(title="Collections cases opened, by month", unit="count", x=months,
                    lines=[Line(name="Cases opened", values=case_vals)], suppressed=case_supp, note="Months with cases from fewer than 10 customers are hidden.",
                    source=_sql_src("Cases opened by month", cases_sql))]),
        ],
        actions=actions,
    )


# ------------------------------------------------------------------ analyst: a cohort (aggregates only)
CURVE_DAYS = (7, 14, 30, 60, 90)


def _bucket(col: str) -> str:
    return f"CASE WHEN {col} <= 0 THEN 0 WHEN {col} <= 30 THEN 1 WHEN {col} <= 60 THEN 2 WHEN {col} <= 90 THEN 3 ELSE 4 END"


def _analyst_cohort(s: Session, cid: str) -> TrackView:
    from semantic.registry import DIMENSIONS, METRICS

    co = parse_cohort(cid)
    k = _min_group()
    cure = next(m for m in METRICS if m.id == "cure_rate")
    kept = next(m for m in METRICS if m.id == "promise_kept_rate")
    cure_where = " AND ".join([*cure.where, co["where"]])
    matured = f"c.case_open_date <= DATE '{_as_of() - dt.timedelta(days=30)}'"
    size_sql = f"SELECT count(*) AS cases, count(DISTINCT x.golden_id) AS customers FROM collections_cases c LEFT JOIN identity.case_xref x ON x.case_id = c.case_id WHERE {co['where']}"
    head_sql = f"SELECT {cure.select.replace('{cure_days}', '30')} FROM {cure.base} WHERE {cure_where} AND {matured}"
    overall_sql = f"SELECT {cure.select.replace('{cure_days}', '30')} FROM {cure.base} WHERE {' AND '.join(cure.where)} AND {matured}"
    curve_cols = ", ".join(
        f"round(100.0 * avg(CASE WHEN c.cure_flag AND c.days_to_cure <= {d} THEN 1 ELSE 0 END) FILTER (WHERE c.case_open_date <= DATE '{_as_of() - dt.timedelta(days=d)}'), 1) AS cure_d{d}, "
        f"count(*) FILTER (WHERE c.case_open_date <= DATE '{_as_of() - dt.timedelta(days=d)}') AS n_cure_d{d}, "
        f"round(100.0 * avg(CASE WHEN {_bucket(f'c.dpd_at_day_{d}')} > {_bucket('c.entry_dpd')} THEN 1 ELSE 0 END) FILTER (WHERE c.dpd_at_day_{d} IS NOT NULL), 1) AS roll_d{d}, "
        f"count(c.dpd_at_day_{d}) AS n_roll_d{d}" for d in CURVE_DAYS)
    curve_sql = f"SELECT {curve_cols} FROM {cure.base} WHERE {cure_where}"
    months = _months_back(12)
    month_expr = next(d for d in DIMENSIONS if d.id == "month").expr["c"]
    monthly_sql = (f"SELECT strftime({month_expr}, '%Y-%m') AS month, {cure.select.replace('{cure_days}', '30')} FROM {cure.base} "
                   f"WHERE {cure_where} AND {matured} AND c.case_open_date >= DATE '{months[0]}-01' GROUP BY 1 ORDER BY 1")
    kept_where = " AND ".join([*kept.where, co["where"]])
    kept_sql = (f"SELECT strftime(date_trunc('month', p.ptp_due_date), '%Y-%m') AS month, {kept.select} FROM {kept.base} "
                f"JOIN collections_cases c ON c.case_id = p.case_id WHERE {kept_where} AND p.ptp_due_date >= DATE '{months[0]}-01' "
                f"AND p.ptp_due_date <= DATE '{_as_of()}' GROUP BY 1 ORDER BY 1")
    driver_dims = [d for d in DIMENSIONS if d.id in ("primary_product", "strategy", "test_cell", "province") and "c" in d.expr and not d.joins.get("c")]
    skip = {"product": "primary_product", "strategy": "strategy", "province": "province"}.get(co["dim"])
    driver_dims = [d for d in driver_dims if d.id != skip]
    drivers_sql = " UNION ALL ".join(
        f"SELECT '{d.id}' AS driver, CAST({d.expr['c']} AS VARCHAR) AS grp, {cure.select.replace('{cure_days}', '30')} FROM {cure.base} WHERE {cure_where} AND {matured} GROUP BY 1, 2"
        for d in driver_dims) + " UNION ALL " + (
        f"SELECT 'hardship_flag' AS driver, CAST(c.hardship_flag AS VARCHAR) AS grp, {cure.select.replace('{cure_days}', '30')} FROM {cure.base} WHERE {cure_where} AND {matured} GROUP BY 1, 2")
    with _W() as w:
        size = w.q(size_sql)[0]
        if (size["customers"] or 0) < k:
            raise _deny(f"This cohort has fewer than {k} customers, so it is hidden (small-group suppression).")
        head = w.q(head_sql)[0]
        overall = w.q(overall_sql)[0]
        curve = w.q(curve_sql)[0]
        monthly = {r["month"]: r for r in w.q(monthly_sql)}
        kept_m = {r["month"]: r for r in w.q(kept_sql)}
        drivers = w.q(drivers_sql)
        strategies = [r["strategy_code"] for r in w.q("SELECT strategy_code FROM collections_cases WHERE strategy_code IS NOT NULL GROUP BY 1 ORDER BY count(*) DESC")]
    period = co["dim"] in ("month", "week")
    cure_curve = [(curve[f"cure_d{d}"] / 100 if curve[f"n_cure_d{d}"] >= k and curve[f"cure_d{d}"] is not None else None) for d in CURVE_DAYS]
    roll_curve = [(curve[f"roll_d{d}"] / 100 if curve[f"n_roll_d{d}"] >= k and curve[f"roll_d{d}"] is not None else None) for d in CURVE_DAYS]
    supp_curve = sum(v is None for v in cure_curve + roll_curve)
    m_vals, m_supp = [], 0
    for m in months:
        r = monthly.get(m)
        ok = r and r["cases"] >= k
        m_supp += 1 if r and not ok else 0
        m_vals.append(r["cure_rate_pct"] / 100 if ok else None)
    kp_vals, kp_supp = [], 0
    for m in months:
        r = kept_m.get(m)
        ok = r and r["promises"] >= k
        kp_supp += 1 if r and not ok else 0
        kp_vals.append(r["promise_kept_rate_pct"] / 100 if ok else None)
    shown_drivers = [d for d in drivers if (d["cases"] or 0) >= k]
    hidden_drivers = len(drivers) - len(shown_drivers)
    shown_drivers.sort(key=lambda d: (d["driver"], -(d["cases"] or 0)))
    label_dim = {"primary_product": "Product", "strategy": "Strategy", "test_cell": "Test cell", "province": "Province", "current_bucket": "Current bucket", "hardship_flag": "Hardship flag"}
    driver_rows = [[label_dim.get(d["driver"], d["driver"]), d["grp"] if d["grp"] is not None else "not set",
                    (d["cure_rate_pct"] / 100) if d["cure_rate_pct"] is not None else None, d["cases"],
                    "causal only within randomised cells" if d["driver"] == "test_cell" else
                    "observed, not causal; compare within a stage" if d["driver"] == "strategy" else "observed, not causal"] for d in shown_drivers]
    total_kept = [kept_m[m] for m in months if m in kept_m]
    kp_n = sum(r["promises"] for r in total_kept)
    kp_rate = sum(r["promise_kept_rate_pct"] * r["promises"] for r in total_kept) / kp_n / 100 if kp_n >= k else None
    ins: list[Insight] = []
    c30, o30 = head.get("cure_rate_pct"), overall.get("cure_rate_pct")
    if c30 is not None and (head.get("cases") or 0) >= k:
        diff = (c30 - o30) if o30 is not None else None
        ins.append(Insight(id="cure", title=f"30-day cure rate {c30:.1f}%" + (f" against {o30:.1f}% for all cases" if o30 is not None else ""),
                           reason=f"Certified cure_rate metric (insolvency and deceased holds excluded) on {head['cases']:,} matured cases (opened at least 30 days before the snapshot). Observed, not causal.",
                           tone="good" if diff is not None and diff > 1 else "warn" if diff is not None and diff < -1 else "info", source=_sql_src("Cohort 30-day cure rate (semantic layer)", head_sql)))
    elif c30 is None or (head.get("cases") or 0) < k:
        ins.append(Insight(id="cure", title="Too new for a 30-day cure rate", reason="Fewer than 10 cases in this cohort have had 30 days since opening.", source=_sql_src("Cohort 30-day cure rate", head_sql)))
    r30 = roll_curve[CURVE_DAYS.index(30)]
    if r30 is not None:
        ins.append(Insight(id="roll", title=f"{r30 * 100:.1f}% were in a worse bucket by day 30",
                           reason="Share of cases whose days past due at day 30 fell in a worse bucket (1-30, 31-60, 61-90, 90+) than at entry. The certified roll-rate metric compares quarter-end account snapshots; this applies the same idea to each case's own day-30 checkpoint.",
                           tone="warn" if r30 > 0.3 else "info", source=_sql_src("Roll and cure curve", curve_sql)))
    if kp_rate is not None:
        ins.append(Insight(id="kept", title=f"Promise kept rate {kp_rate * 100:.1f}% over the last 12 months",
                           reason=f"Certified promise_kept_rate metric on {kp_n:,} resolved promises on this cohort's cases.", source=_sql_src("Promise kept rate by month (semantic layer)", kept_sql)))
    by = {}
    for d in shown_drivers:
        if d["cure_rate_pct"] is not None:
            by.setdefault(d["driver"], []).append(d)
    # strategy codes change as a case rolls to the next stage, so they are compared on the scorecard (within a stage), not here
    gaps = [(max(v, key=lambda x: x["cure_rate_pct"]), min(v, key=lambda x: x["cure_rate_pct"]), dd) for dd, v in by.items() if len(v) >= 2 and dd != "strategy"]
    if gaps:
        hi, lo, dd = max(gaps, key=lambda t: t[0]["cure_rate_pct"] - t[1]["cure_rate_pct"])
        ins.append(Insight(id="driver", title=f"Biggest gap by {label_dim.get(dd, dd).lower()}: {hi['grp']} {hi['cure_rate_pct']:.1f}% vs {lo['grp']} {lo['cure_rate_pct']:.1f}%",
                           reason="The 30-day cure rate differs most across this breakdown. Observed, not causal: a randomised test would show whether changing the strategy changes the outcome.",
                           tone="info", source=_sql_src("Cure rate by driver (certified dimensions)", drivers_sql)))
    mine = [p for p in _proposals() if p["subject_id"] == cid]
    actions = [Action(id="propose", kind="propose_test", label="Propose a strategy test for this cohort", endpoint=f"/track/cohort/{cid}/propose", target=cid,
                      options=[Fact(label=st, value=st) for st in strategies],
                      detail="Creates a proposal for a team lead to approve. Nothing is sent and no case changes. Written to the audit log.")]
    sections = [
        Section(id="curves", label="Cure and roll", kind="series", series=[
            Series(title="Cure and roll by days since the case opened", unit="pct", x=[f"Day {d}" for d in CURVE_DAYS],
                   lines=[Line(name="Cured by then", values=cure_curve), Line(name="In a worse bucket than at entry", values=roll_curve)],
                   suppressed=supp_curve, note="Each point counts only cases old enough to have reached that day; points under 10 cases are hidden.",
                   source=_sql_src("Roll and cure curve", curve_sql))]),
    ]
    if not period:
        sections.append(Section(id="monthly", label="Over time", kind="series", series=[
            Series(title="30-day cure rate by month opened", unit="pct", x=months, lines=[Line(name="30-day cure rate", values=m_vals)], suppressed=m_supp,
                   note="Only months whose cases have all had 30 days. Months under 10 cases are hidden.", source=_sql_src("Cure rate by month opened (semantic layer)", monthly_sql)),
            Series(title="Promise kept rate by month due", unit="pct", x=months, lines=[Line(name="Promise kept rate", values=kp_vals)], suppressed=kp_supp,
                   note="Months under 10 promises are hidden.", source=_sql_src("Promise kept rate by month (semantic layer)", kept_sql))]))
    else:
        sections.append(Section(id="monthly", label="Promises", kind="series", series=[
            Series(title="Promise kept rate by month due, for this cohort's cases", unit="pct", x=months, lines=[Line(name="Promise kept rate", values=kp_vals)], suppressed=kp_supp,
                   note="Months under 10 promises are hidden.", source=_sql_src("Promise kept rate by month (semantic layer)", kept_sql))]))
    sections.append(Section(id="drivers", label="Drivers", kind="table", intro="30-day cure rate by certified breakdowns inside this cohort. Groups under 10 cases are hidden.",
                            tables=[Table(columns=["Breakdown", "Group", "30-day cure rate", "Cases", "How to read it"], rows=driver_rows,
                                          note=f"{hidden_drivers} group(s) hidden (fewer than {k} cases)." if hidden_drivers else None,
                                          source=_sql_src("Cure rate by driver (certified dimensions)", drivers_sql))]))
    sections.append(Section(id="proposals", label="Proposals", kind="table", intro="Strategy tests proposed for this cohort. Read-only here: a team lead approves or rejects them.",
                            tables=[Table(columns=["Proposal", "Strategy", "Status", "Proposed", "Decided by"],
                                          rows=[[p["proposal_id"], p["payload"].get("strategy_code"), p["status"].replace("_", " "), _day(p["created_ts"]), p["decided_by"]] for p in mine],
                                          source=Source(kind="records", label="Playbook proposals (ops store)", table="ops.playbook_proposals", ids=[p["proposal_id"] for p in mine]))]))
    return TrackView(
        meta=_meta(), kind="cohort", id=cid, title=co["label"], aggregates_only=True,
        subtitle=f"Aggregates only · groups under {k} hidden · as of {_as_of()}",
        figures=[Fact(label="Cases", value=f"{size['cases']:,}"), Fact(label="Customers", value=f"{size['customers']:,}"),
                 Fact(label="30-day cure", value=f"{c30:.1f}%" if c30 is not None and (head.get('cases') or 0) >= k else "n/a"),
                 Fact(label="Promise kept", value=f"{kp_rate * 100:.1f}%" if kp_rate is not None else "n/a")],
        insights=ins, sections=sections, actions=actions,
    )


def _proposals() -> list[dict]:
    from decisioning import playbooks

    return [p for p in playbooks.listing() if p["playbook"] == "strategy_test"]


def propose_test(s: Session, cid: str, strategy_code: str, note: str | None) -> Proposed:
    """Analyst: propose a strategy test on a cohort. Stored through the playbook store (a team lead approves it with the
    existing /playbooks/{id}/approve endpoint) and written to the audit log. Contacts nobody, changes no case."""
    from common.hashing import stable_hash
    from decisioning import playbooks

    _check_kind(s, "cohort")
    co = parse_cohort(cid)
    if not re.fullmatch(r"[A-Z][A-Z0-9-]{1,40}", strategy_code or ""):
        raise _deny("Pick a strategy code from the list.", 422)
    with _W() as w:
        known = {r["strategy_code"] for r in w.q("SELECT DISTINCT strategy_code FROM collections_cases WHERE strategy_code IS NOT NULL")}
        size = w.q(f"SELECT count(*) AS cases, count(DISTINCT x.golden_id) AS customers FROM collections_cases c LEFT JOIN identity.case_xref x ON x.case_id = c.case_id WHERE {co['where']}")[0]
    if strategy_code not in known:
        raise _deny("That strategy code does not exist.", 422)
    if (size["customers"] or 0) < _min_group():
        raise _deny(f"This cohort has fewer than {_min_group()} customers, so it is hidden (small-group suppression).")
    pid = f"ST-{stable_hash([cid, strategy_code])[:10].upper()}"
    if playbooks.get(pid):
        raise _deny("This test has already been proposed for this cohort.", 409)
    proposal = {"proposal_id": pid, "playbook": "strategy_test", "kind": "strategy_test", "subject_id": cid,
                "title": f"Test strategy {strategy_code} on {co['label'].lower()}",
                "detail": (f"Proposed by analyst {s.user_id}: a randomised test of {strategy_code} on this cohort ({size['cases']:,} cases, "
                           f"{size['customers']:,} customers). Today's results are observed, not causal; a randomised test would show the effect. "
                           + (f"Note: {note.strip()[:300]}" if note and note.strip() else "")).strip(),
                "payload": {"cohort": cid, "strategy_code": strategy_code, "n_cases": size["cases"], "n_customers": size["customers"],
                            "proposed_by": s.user_id, "label": "observed, not causal"}}
    audit_id = audit.record(
        s.user_id, _role(s), "strategy_test_propose", "playbook_proposal", pid,
        {"cohort": cid, "strategy_code": strategy_code, "note": note}, {"proposal_id": pid, "status": playbooks.PENDING, "contacts_anyone": False})
    playbooks.store([proposal])
    return Proposed(audit_id=audit_id, proposal_id=pid, status=playbooks.PENDING,
                    note="Proposed. A team lead sees it under Team, Playbooks; nothing is sent and no case changes.")


# ------------------------------------------------------------------ steward: a golden customer's identity (no calls, no notes)
def _steward_identity(s: Session, g: str) -> TrackView:
    with _W() as w:
        cust = w.q("SELECT golden_id, crm_customer_ids, match_method, match_confidence, source_systems, accounts, open_cases FROM c360_customer WHERE golden_id = ?", [g])
        if not cust:
            raise _deny("No customer with that ID.", 404)
        xref_sql = f"SELECT source_system, source_ref, match_method, match_probability, evidence FROM identity.identity_xref WHERE golden_id = '{g}' ORDER BY source_system, source_ref"
        xref = w.q(xref_sql)
        crm = w.q("SELECT crm_customer_id, cluster_size, link_evidence, review_flag FROM identity.crm_golden WHERE golden_id = ?", [g])
        pairs = w.q("SELECT pair_id, source_system, source_ref, score, reason FROM identity.review_queue WHERE candidate_golden_id = ? ORDER BY score DESC", [g])
    c = cust[0]
    reviews = {}
    if pairs:
        ph = ",".join("?" * len(pairs))
        reviews = {r["pair_id"]: r for r in _ops(f"SELECT pair_id, verdict, reviewer_id, ts FROM identity_reviews WHERE pair_id IN ({ph})", tuple(p["pair_id"] for p in pairs))}
    systems = sorted({x["source_system"] for x in xref})
    per_sys = []
    for sy in systems:
        rows = [x for x in xref if x["source_system"] == sy]
        probs = [float(x["match_probability"]) for x in rows if x["match_probability"] is not None]
        per_sys.append([SYSTEM_LABEL.get(sy, sy), len(rows), ", ".join(sorted({x["match_method"] for x in rows})),
                        round(min(probs), 3) if probs else None, round(sum(probs) / len(probs), 3) if probs else None])
    ev: list[Event] = []
    if len(crm) > 1:
        ev.append(Event(ts=_iso(get_settings().as_of_date), type="merge", title=f"{len(crm)} CRM records merged into one golden ID",
                        detail="; ".join(f"{r['crm_customer_id']} ({r['link_evidence']})" for r in crm), ref=g, table="identity.crm_golden"))
    for p in pairs:
        r = reviews.get(p["pair_id"])
        ev.append(Event(ts=_iso(r["ts"]) if r and r["ts"] else _iso(get_settings().as_of_date), type="review",
                        title=f"Grey-band link {p['source_system']}:{p['source_ref']} (score {float(p['score']):.2f})",
                        detail=(f"Steward verdict {r['verdict']} by {r['reviewer_id']}" if r else f"Waiting for review: {p['reason']}"),
                        ref=p["pair_id"], table="identity.review_queue", tone="good" if r else "warn"))
    audit_rows = []
    if pairs:
        for p in pairs:
            audit_rows += audit.query(limit=20, entity_type="identity_pair", entity_id=p["pair_id"])
    for a in audit_rows:
        ev.append(Event(ts=_iso(a["ts"]), type="review", title="Identity verdict recorded", detail=f"by {a['user_id']}", ref=str(a["audit_id"]), table="ops.audit_log", tone="good"))
    tests, issues, drift_ev = _quality_for([SYSTEM_TABLES.get(sy, sy) for sy in systems] + ["c360_customer"])
    ev += drift_ev
    ev.sort(key=lambda e: e.ts, reverse=True)
    low = [x for x in xref if x["match_probability"] is not None and float(x["match_probability"]) < 0.95]
    ins = [Insight(id="confidence", title=f"{len(xref)} source keys from {len(systems)} systems, overall confidence {float(c['match_confidence']):.3f}",
                   reason=f"Match method: {c['match_method']}. Deterministic links share an exact key; probabilistic links come from the Splink-style scorer (precision first, because a false merge means calling the wrong person).",
                   tone="info", source=_sql_src("Identity cross-reference", xref_sql))]
    if low:
        ins.append(Insight(id="low", title=f"{len(low)} link(s) below 0.95 confidence", reason="Lower-confidence links are the ones to check first if this customer's data looks wrong.",
                           tone="warn", source=_rec_src("Low-confidence links", "identity.identity_xref", [f"{x['source_system']}:{x['source_ref']}" for x in low])))
    waiting = [p for p in pairs if p["pair_id"] not in reviews]
    ins.append(Insight(id="pairs", title=f"{len(waiting)} grey-band pair(s) waiting for you" if pairs else "No grey-band pair for this customer",
                       reason="A grey-band pair is linked only after a steward says so; the verdict applies on the next identity run.",
                       tone="warn" if waiting else "good", source=_rec_src("Review queue", "identity.review_queue", [p["pair_id"] for p in pairs])))
    failing = [t for t in tests if t[1] not in ("pass", "success")]
    ins.append(Insight(id="tests", title=f"{len(tests) - len(failing)} of {len(tests)} contract test(s) passing on gold.c360_customer",
                       reason="Contract tests run in the nightly build before the warehouse is published.", tone="warn" if failing else "good",
                       source=Source(kind="report", label="reports/contract_tests.json (dbt run results)", table="gold.c360_customer")))
    actions = [Action(id=f"pair-{p['pair_id']}", kind="identity_verdict", label=f"Decide pair {p['pair_id']} ({p['source_system']}:{p['source_ref']}, score {float(p['score']):.2f})",
                      endpoint=f"/steward/identity/{p['pair_id']}", target=p["pair_id"], enabled=p["pair_id"] not in reviews,
                      why_disabled="Already decided." if p["pair_id"] in reviews else None,
                      options=[Fact(label="Link (merge)", value="link"), Fact(label="Do not link (keep apart)", value="no_link"), Fact(label="Unsure", value="unsure")],
                      detail="Applied on the next identity run. Audited.") for p in pairs[:10]]
    actions.append(Action(id="queue", kind="link", label="Open the identity review queue", link="/steward/identity"))
    return TrackView(
        meta=_meta(), kind="identity", id=g, title=f"Identity {g}", golden_id=g,
        subtitle="Lineage and match confidence only. Stewards never see a customer's calls, notes or summaries.",
        figures=[Fact(label="Source keys", value=str(len(xref))), Fact(label="Systems", value=str(len(systems))),
                 Fact(label="Confidence", value=f"{float(c['match_confidence']):.3f}"), Fact(label="CRM records", value=str(len(crm)))],
        insights=ins,
        sections=[
            Section(id="lineage", label="Lineage", kind="table", tables=[
                Table(title="Match confidence per source system", columns=["System", "Keys", "Method", "Lowest confidence", "Average confidence"], rows=per_sys, source=_sql_src("Identity cross-reference", xref_sql)),
                Table(title="Every source key", columns=["System", "Source key", "Method", "Confidence", "Evidence"],
                      rows=[[SYSTEM_LABEL.get(x["source_system"], x["source_system"]), x["source_ref"], x["match_method"],
                             round(float(x["match_probability"]), 3) if x["match_probability"] is not None else None, x["evidence"]] for x in xref],
                      source=_sql_src("Identity cross-reference", xref_sql))]),
            Section(id="history", label="Merges and reviews", kind="timeline", events=ev,
                    intro="CRM records merged into this golden ID, grey-band pairs and steward verdicts, plus schema changes on its source tables."),
            Section(id="quality", label="Tests and quality", kind="table", tables=[
                Table(title="Contract tests on gold.c360_customer", columns=["Test", "Status", "Failures", "Run"], rows=tests,
                      source=Source(kind="report", label="reports/contract_tests.json", table="gold.c360_customer")),
                Table(title="Known quality issues on this customer's source tables", columns=["Tables", "Issue", "Records affected", "How it is handled"], rows=issues,
                      source=Source(kind="report", label="reports/data_quality.json", table=", ".join(SYSTEM_TABLES.get(sy, sy) for sy in systems)))]),
        ],
        actions=actions,
    )


def _quality_for(tables: list[str]) -> tuple[list[list], list[list], list[Event]]:
    """Contract tests on c360_customer, data quality issues and drift events that touch any of these tables."""
    from governance import drift

    rep = get_settings().reports_dir
    tests, issues, ev = [], [], []
    names = {t.split(".")[-1] for t in tables}
    rr = json.loads((rep / "contract_tests.json").read_text()) if (rep / "contract_tests.json").exists() else {}
    run = (rr.get("metadata") or {}).get("generated_at", "")[:16].replace("T", " ")
    for r in rr.get("results", []):
        uid = r.get("unique_id", "")
        if uid.startswith("test.") and ("c360_customer" in uid or uid.split(".")[2].startswith("contract_")) and "c360_customer" in names:
            tests.append([uid.split(".")[2], r.get("status"), r.get("failures") or 0, run])
    dq = json.loads((rep / "data_quality.json").read_text()) if (rep / "data_quality.json").exists() else {}
    for i in dq.get("issues", []):
        tabs = {t.strip() for t in str(i.get("tables", "")).split(",")}
        short = {t.replace("_accounts", "").removeprefix("stg_") for t in names} | {t.removeprefix("stg_") for t in names} | names
        if tabs & short:
            issues.append([i.get("tables"), i.get("issue"), i.get("records_affected"), i.get("handled")])
    for f in drift.fixes():
        if f["table"] in names:
            ev.append(Event(ts=_iso(f.get("created_ts")), type="drift", title=f"Schema change on {f['table']}: {f['description']}"[:160],
                            detail=f"Fix {f['fix_id']} is {f['status'].replace('_', ' ')}", ref=f["fix_id"], table="ops.drift_fixes", tone="warn" if f["status"] == drift.PENDING else "info"))
    with _W() as w:
        for e in w.q("SELECT event_id, event_type, description, affected_tables, start_ts FROM ops_events ORDER BY start_ts"):
            aff = set(json.loads(e["affected_tables"])) if str(e["affected_tables"]).startswith("[") else set()
            if aff & names:
                ev.append(Event(ts=_iso(e["start_ts"]), type="drift" if e["event_type"] in ("platform_release", "data_feed_issue") else "quality",
                                title=f"{e['event_id']}: {e['description']}", detail=f"{e['event_type'].replace('_', ' ')}; tables {', '.join(sorted(aff))}",
                                ref=e["event_id"], table="silver.ops_events", tone="warn"))
    return tests, issues, ev


# ------------------------------------------------------------------ steward: a data product
def _steward_product(s: Session, name: str) -> TrackView:
    from governance import drift

    man = _manifest()
    uid = _products()[name]
    node = man["nodes"][uid]
    parents = [p for p in man["parent_map"].get(uid, [])]
    children = [c for c in man["child_map"].get(uid, []) if not c.startswith("test.")]
    tests_ids = [c for c in man["child_map"].get(uid, []) if c.startswith("test.")]
    rep = get_settings().reports_dir
    rr = json.loads((rep / "contract_tests.json").read_text()) if (rep / "contract_tests.json").exists() else {}
    run = (rr.get("metadata") or {}).get("generated_at", "")[:16].replace("T", " ")
    status = {r["unique_id"]: r for r in rr.get("results", [])}
    tests = [[t.split(".")[2], status.get(t, {}).get("status", "not in the last run"), status.get(t, {}).get("failures") or 0, run if t in status else ""] for t in tests_ids]
    build = status.get(uid, {}).get("status")
    bare = node["name"]
    _, issues, ev = _quality_for([bare] + [man["nodes"][p]["name"] for p in parents if p in man["nodes"]])
    with _W() as w:
        size = w.q("SELECT estimated_size AS n FROM duckdb_tables() WHERE schema_name = ? AND table_name = ?", [node["schema"], bare])
        cols = w.q("SELECT count(*) AS n FROM duckdb_columns() WHERE schema_name = ? AND table_name = ?", [node["schema"], bare])
        conf = []
        if name == "gold.c360_customer":
            conf_sql = "SELECT source_system, match_method, count(*) AS keys, round(avg(match_probability), 3) AS avg_confidence, round(min(match_probability), 3) AS min_confidence FROM identity.identity_xref GROUP BY 1, 2 ORDER BY 1, 2"
            conf = w.q(conf_sql)
    pending = [f for f in drift.fixes(drift.PENDING) if f["table"] == bare]
    ev.sort(key=lambda e: e.ts, reverse=True)

    def nm(u: str) -> str:
        n = man["nodes"].get(u) or man.get("sources", {}).get(u) or {}
        return f"{n.get('schema', '')}.{n.get('name', u.split('.')[-1])}".strip(".") if n else u.split(".", 2)[-1]

    failing = [t for t in tests if t[1] not in ("pass", "success", "not in the last run")]
    ins = [Insight(id="build", title=f"Last build: {build or 'not in the last run'}" + (f" ({run})" if run else ""),
                   reason="Built by dbt in the nightly jobs container into a separate file, tested, then published atomically.",
                   tone="good" if build == "success" else "info", source=Source(kind="report", label="reports/contract_tests.json (dbt run results)", table=name)),
           Insight(id="tests", title=f"{len(tests) - len(failing)} of {len(tests)} test(s) passing" if tests else "No tests attached to this table",
                   reason="dbt tests and contract tests attached to this model in the manifest.", tone="warn" if failing else ("good" if tests else "info"),
                   source=Source(kind="report", label="pipeline/target/manifest.json child_map", table=name, ids=[t[0] for t in tests])),
           Insight(id="quality", title=f"{len(issues)} known quality issue(s), {len(ev)} incident or schema-change event(s)",
                   reason="From the data quality report and the ops events log; schema changes get a drafted fix that only a steward approves.",
                   tone="warn" if pending else "info", source=Source(kind="report", label="reports/data_quality.json and silver.ops_events", table=name))]
    if pending:
        ins.append(Insight(id="drift", title=f"{len(pending)} drafted schema fix(es) waiting for you", reason="The app never applies a fix; an engineer does, after you approve.",
                           tone="warn", source=_rec_src("Drafted fixes", "ops.drift_fixes", [f["fix_id"] for f in pending])))
    actions = [Action(id=f"fix-{f['fix_id']}", kind="drift_approve", label=f"Approve fix {f['fix_id']}", endpoint=f"/drift/{f['fix_id']}/approve", target=f["fix_id"],
                      detail=f["description"]) for f in pending]
    actions.append(Action(id="drift", kind="link", label="Open schema changes", link="/steward/drift"))
    actions.append(Action(id="quality", kind="link", label="Open the data quality report", link="/governance/quality"))
    sections = [
        Section(id="lineage", label="Lineage", kind="table", tables=[
            Table(title="Built from", columns=["Upstream", "Type"], rows=[[nm(p), p.split(".")[0]] for p in parents], source=Source(kind="report", label="pipeline/target/manifest.json parent_map", table=name)),
            Table(title="Used by", columns=["Downstream", "Type"], rows=[[nm(c), c.split(".")[0]] for c in children], source=Source(kind="report", label="pipeline/target/manifest.json child_map", table=name))]),
        Section(id="tests", label="Contract tests", kind="table", tables=[Table(columns=["Test", "Status", "Failures", "Run"], rows=tests,
                note="One recorded run is kept in reports/contract_tests.json; each nightly build replaces it.", source=Source(kind="report", label="reports/contract_tests.json", table=name))]),
        Section(id="events", label="Quality and drift", kind="timeline", events=ev, intro="Incidents, feed issues, releases and drafted schema fixes that touch this table."),
        Section(id="issues", label="Known issues", kind="table", tables=[Table(columns=["Tables", "Issue", "Records affected", "How it is handled"], rows=issues,
                source=Source(kind="report", label="reports/data_quality.json", table=name))]),
    ]
    if conf:
        sections.insert(1, Section(id="confidence", label="Match confidence", kind="table", tables=[Table(title="Match confidence per source system",
                        columns=["System", "Method", "Keys", "Average confidence", "Lowest confidence"],
                        rows=[[SYSTEM_LABEL.get(r["source_system"], r["source_system"]), r["match_method"], r["keys"], r["avg_confidence"], r["min_confidence"]] for r in conf],
                        source=_sql_src("Match confidence per source system", conf_sql))]))
    return TrackView(
        meta=_meta(), kind="product", id=name, title=name, aggregates_only=True,
        subtitle=(node.get("description") or "").split("\n")[0][:200] or f"dbt model {uid}",
        figures=[Fact(label="Rows (estimate)", value=f"{int(size[0]['n']):,}" if size and size[0]["n"] is not None else "view"),
                 Fact(label="Columns", value=str(cols[0]["n"]) if cols else "n/a"), Fact(label="Upstream", value=str(len(parents))), Fact(label="Tests", value=str(len(tests)))],
        insights=ins, sections=sections, actions=actions,
    )
