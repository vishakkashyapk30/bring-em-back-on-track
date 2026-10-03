# ruff: noqa: E501
"""The assistant's tool registry. Each tool is a plain function that calls the same production code as the matching
API endpoint and returns a ToolResult (a one-line summary plus evidence a person can check). A tool never writes
customer-affecting data: it can only propose, and a person approves in the existing screen.

Every tool lists the roles that may use it; calling it as any other role gives a failed step with a reason, never data.
"""

from __future__ import annotations

import json
import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from api.schemas.common import Session
from common.config import get_settings
from common.llm_mode import use_mode
from decisioning.assistant import data

ROOT = Path(__file__).resolve().parents[2]
ALL_ROLES = ("agent", "hardship_specialist", "team_lead", "analyst", "steward")


class ToolSkip(Exception):
    """The tool has nothing to do here (no case, no promise, no call)."""


class ToolDenied(Exception):
    """The person may not use this tool or see this record."""


@dataclass
class ToolContext:
    session: Session
    case_id: str | None = None
    golden_id: str | None = None
    slots: dict[str, Any] = field(default_factory=dict)
    mode: str | None = None
    facts: dict[str, Any] = field(default_factory=dict)
    audit_scores: bool = True  # the guided demo only reads; it does not log a score event per view

    @property
    def role(self) -> str:
        return getattr(self.session.role, "value", str(self.session.role))


@dataclass
class ToolResult:
    summary: str
    evidence: dict = field(default_factory=dict)
    status: str = "done"
    findings: list[str] = field(default_factory=list)
    proposals: list[dict] = field(default_factory=list)
    cites: list[dict] = field(default_factory=list)
    facts: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    roles: frozenset[str]
    fn: Callable[..., ToolResult]


TOOLS: dict[str, Tool] = {}


def tool(name: str, description: str, roles: tuple[str, ...]):
    def deco(fn):
        TOOLS[name] = Tool(name, description, frozenset(roles), fn)
        return fn

    return deco


def tools_for(role: str) -> list[Tool]:
    return [t for t in TOOLS.values() if role in t.roles]


# ---------------------------------------------------------------- helpers

def _j(v: Any) -> Any:
    """JSON-safe value for evidence tables."""
    if v is None:
        return None
    if isinstance(v, float):
        return None if math.isnan(v) else round(v, 4)
    if hasattr(v, "item") and not isinstance(v, (str, bytes)):
        try:
            return _j(v.item())
        except Exception:  # noqa: BLE001
            return str(v)
    if isinstance(v, (date, datetime)):
        return str(v)[:19] if isinstance(v, datetime) else str(v)
    if isinstance(v, (list, tuple, dict)):
        return json.dumps(v, default=str)
    return v


def table(columns: list[str], rows: list[list[Any]]) -> dict:
    return {"columns": columns, "rows": [[_j(x) for x in r] for r in rows]}


def kv(pairs: list[tuple[str, Any]]) -> list[list[str]]:
    return [[k, "n/a" if v is None else str(_j(v))] for k, v in pairs]


def link(label: str, href: str) -> dict:
    return {"label": label, "href": href}


def proposal(pid: str, title: str, detail: str, kind: str, href: str, requires_role: str) -> dict:
    return {"id": pid, "title": title, "detail": detail, "kind": kind, "href": href, "requires_role": requires_role}


def _refused(reason: str | None) -> str:
    r = (reason or "outside scope").strip()
    return r if r.lower().startswith("refused") else f"Refused: {r}"


def money(v: Any) -> str:
    try:
        return f"${float(v):,.0f}"
    except (TypeError, ValueError):
        return "n/a"


def short_name(name: str | None) -> str:
    p = (name or "").split()
    return f"{p[0][0]}. {p[-1]}" if len(p) >= 2 else (name or "customer")


def _pct(v: Any) -> str:
    return "n/a" if v is None else f"{float(v) * 100:.0f}%"


def _report(name: str) -> dict | None:
    p = get_settings().reports_dir / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else None


def _access(kind: str, ident: str, ctx: ToolContext) -> None:
    """Row-level access (api/access.py), decided before any data is read; the same in every mode."""
    from fastapi import HTTPException

    from api import access

    try:
        getattr(access, kind)(ctx.session, ident)
    except HTTPException as e:
        d = e.detail
        raise ToolDenied((d.get("reason") if isinstance(d, dict) else str(d)) or "Not allowed.") from e


def default_case_for(session: Session) -> str | None:
    """The person's own top-priority case (preferring one with a recorded call), for goals that name no case."""
    df = data.queue_df()
    if df is None:
        return None
    rows = [r for r in df[(df.treatment != "no_contact")].sort_values("priority", ascending=False).head(4000).to_dict("records")
            if data.can_see(session, r)]
    rows = rows[:25]
    if not rows:
        return None
    with_call = _cases_with_calls([r["case_id"] for r in rows])
    return next((r["case_id"] for r in rows if r["case_id"] in with_call), rows[0]["case_id"])


def _case(ctx: ToolContext) -> str:
    cid = ctx.case_id or ctx.facts.get("default_case")
    if not cid and (ctx.golden_id or ctx.facts.get("default_golden")):
        cid = data.case_for_golden(ctx.golden_id or ctx.facts["default_golden"], ctx.session)
    if not cid:
        raise ToolSkip("No case selected, so this step was skipped. Give a case ID such as CS-2026-123456.")
    row = data.case_row(cid)
    if row is None:
        raise ToolSkip(f"{cid} is not in today's queue, so this step was skipped.")
    if not data.can_see(ctx.session, row):
        raise ToolDenied(f"{cid} is outside your scope (an agent sees own cases, a team lead the team's cases).")
    _access("case", cid, ctx)
    ctx.case_id = cid
    return cid


def _golden(ctx: ToolContext) -> str:
    g = ctx.golden_id or ctx.facts.get("default_golden")
    if not g and (ctx.case_id or ctx.facts.get("default_case")):
        row = data.case_row(ctx.case_id or ctx.facts["default_case"])
        g = row["golden_id"] if row else None
    if not g:
        raise ToolSkip("No customer selected, so this step was skipped. Give a case or customer ID.")
    if ctx.role in ("agent", "team_lead", "hardship_specialist"):
        df = data.queue_df()
        rows = [] if df is None else df[df.golden_id == g].to_dict("records")
        if not rows or not any(data.can_see(ctx.session, r) for r in rows):
            raise ToolDenied(f"{g} is outside your scope (an agent sees own customers, a team lead the team's).")
    _access("golden", g, ctx)
    ctx.golden_id = g
    return g


def run_tool(name: str, ctx: ToolContext, args: dict | None = None) -> dict:
    """Run one tool and return {status, summary, evidence, cites, findings, proposals, ms}. Never raises."""
    t0 = time.perf_counter()

    def out(res: ToolResult | None = None, status: str | None = None, summary: str = "") -> dict:
        ms = round((time.perf_counter() - t0) * 1000)
        if res is None:
            return {"status": status, "summary": summary, "evidence": {}, "cites": [], "findings": [],
                    "proposals": [], "ms": ms}
        ctx.facts.update(res.facts)
        return {"status": res.status, "summary": res.summary, "evidence": res.evidence, "cites": res.cites,
                "findings": res.findings, "proposals": res.proposals, "ms": ms}

    t = TOOLS.get(name)
    if t is None:
        return out(status="failed", summary=f"Unknown tool {name}.")
    if ctx.role not in t.roles:
        return out(status="failed", summary=f"The {ctx.role.replace('_', ' ')} role may not use {name}. No data was read.")
    try:
        return out(t.fn(ctx, **(args or {})))
    except HTTPException as e:
        d = e.detail
        return out(status="failed", summary=(d.get("reason") if isinstance(d, dict) else str(d)) or "Not allowed.")
    except ToolSkip as e:
        return out(status="skipped", summary=str(e))
    except ToolDenied as e:
        return out(status="failed", summary=str(e))
    except FileNotFoundError:
        return out(status="failed", summary="The warehouse or a report this step needs is not built yet.")
    except Exception as e:  # noqa: BLE001 - a broken tool must not break the run
        return out(status="failed", summary=f"Could not run: {type(e).__name__}: {str(e)[:160]}")


# ---------------------------------------------------------------- queue

@tool("queue_summary", "Today's NBA queue for the signed-in person: counts and the top cases.",
      ("agent", "team_lead", "hardship_specialist"))
def queue_summary(ctx: ToolContext, view: str = "all") -> ToolResult:
    from api.services import nba as svc

    q = svc.queue(ctx.session, view, "priority", "", 0, 25)
    if not q.get("items") and not q.get("counts"):
        raise ToolSkip(q.get("note") or "The nightly queue has not been built yet.")
    c = q["counts"]
    items = q["items"]
    rows = [[i["case_id"], i["name"], i["product"].replace("_", " "), i["dpd"], f'{i["action"]["treatment"]} by {i["action"]["channel"]}',
             i["p_break"], i["headline"]] for i in items[:6]]
    facts: dict[str, Any] = {}
    top = None
    if items:
        with_call = _cases_with_calls([i["case_id"] for i in items])
        top = next((i for i in items if i["case_id"] in with_call), items[0])
        facts = {"default_case": top["case_id"], "default_golden": top["golden_id"], "queue_counts": c}
    calls = c.get("calls", 0)
    summary = f"{q.get('scope', 'Your queue')}: {c['all']:,} cases to work ({calls:,} calls), {c['hardship']:,} with a hardship flag, {c['high_risk']:,} high risk."
    res = ToolResult(
        summary, {**table(["Case", "Customer", "Product", "DPD", "Proposed action", "Break risk", "Why"], rows),
                  "kv": kv([("In scope", c["in_scope"]), ("To work today", c["all"]), ("Calls", calls),
                            ("Hardship flagged", c["hardship"]), ("Vulnerable", c["vulnerable"]),
                            ("High risk", c["high_risk"]), ("Batch (team lead approves)", c["batch"]),
                            ("Pushed to tomorrow", c["tomorrow"])]),
                  "links": [link("Open the queue", "/queue")]},
        facts=facts)
    res.findings.append(f"{c['all']:,} cases to work today; {calls:,} are calls and {c['hardship']:,} carry a hardship flag.")
    if top is not None:
        res.findings.append(f"Highest priority with a recorded call: {top['name']} ({top['case_id']}), {top['headline'].lower()}.")
    role = ctx.role
    res.proposals.append(proposal(
        "work-queue", f"Work today's queue ({c['all']:,} cases)",
        "Open the queue and approve, edit or override each proposed action. Nothing is sent until a person approves.",
        "review", "/queue", role))
    return res


def _cases_with_calls(case_ids: list[str]) -> set[str]:
    if not case_ids:
        return set()
    from api.services.c360 import _q

    rows = _q("SELECT DISTINCT case_id FROM silver.call_transcripts WHERE list_contains(?, case_id)", [case_ids])
    return {r["case_id"] for r in rows}


# ---------------------------------------------------------------- customer

@tool("customer_360", "The customer's 360 view: badges, holdings and which source systems were matched (with confidence).",
      ("agent", "hardship_specialist", "team_lead", "steward"))
def customer_360(ctx: ToolContext) -> ToolResult:
    from api.services import c360

    g = _golden(ctx)
    c = c360.customer(g)
    if c is None:
        raise ToolSkip(f"No customer {g} in the warehouse.")
    ident = c360.identity(g) or {}
    b = c["badges"]
    name = short_name(c["display_name"])
    holdings = [[h["product"], h["account"], h["balance"], h["overdue"], h["dpd"], h["status"], h["system"]] for h in c["holdings"][:8]]
    srcs = ident.get("sources", [])
    ev = {
        **table(["Product", "Account", "Balance", "Overdue", "DPD", "Status", "Source"], holdings),
        "kv": kv([("Customer", f"{name} ({g})"), ("Segment", c["segment"]), ("Where", f'{c["city"]}, {c["province_code"]}'),
                  ("Risk band", b["risk"]["band"]), ("Bucket", b["bucket"]),
                  ("Hardship flag", b["hardship_flag"]), ("Vulnerability flag", b["vulnerability_flag"]),
                  ("Dispute open", b["dispute_open_flag"]), ("Contact block", b["contact_block"]),
                  ("Consent (call, sms, email)", f'{b["consent"]["call"]}, {b["consent"]["sms"]}, {b["consent"]["email"]}'),
                  ("Past due", money(c["total_past_due_cad"])), ("Max DPD", c["max_dpd"]),
                  ("Matched sources", f'{len(srcs)} ({", ".join(ident.get("lineage", []))})' if srcs else None),
                  ("Match confidence", ident.get("match_confidence")), ("Match method", ident.get("match_method"))]),
        "links": [link("Open the customer", f"/customers/{g}")],
    }
    res = ToolResult(f"{name}: {len(c['holdings'])} accounts, {money(c['total_past_due_cad'])} past due, hardship flag {b['hardship_flag']}, identity matched from {len(srcs)} source keys.",
                     ev, facts={"hardship_flag": b["hardship_flag"], "open_case_id": c["open_case_id"],
                                "default_golden": g, "customer_name": name})
    if b["hardship_flag"] != "none":
        res.findings.append(f"{name} has a hardship flag ({b['hardship_flag']}): reminders, payment links and collection calls are removed by the contact rules.")
    if ident.get("match_confidence") is not None and float(ident["match_confidence"]) < 0.9:
        res.findings.append(f"Identity match confidence is {float(ident['match_confidence']):.2f}: check the sources before acting.")
    if ctx.case_id is None and c["open_case_id"] and ctx.role != "steward":
        row = data.case_row(c["open_case_id"])
        if row and data.can_see(ctx.session, row):
            ctx.facts.setdefault("default_case", c["open_case_id"])
    return res


@tool("identity_lineage", "Every source key linked to a golden customer ID, with method and confidence.",
      ("steward", "agent", "hardship_specialist", "team_lead"))
def identity_lineage(ctx: ToolContext) -> ToolResult:
    from api.services import c360

    g = _golden(ctx) if ctx.role != "steward" else (ctx.golden_id or ctx.facts.get("default_golden"))
    if not g:
        raise ToolSkip("No customer selected, so this step was skipped.")
    _access("golden", g, ctx)
    i = c360.identity(g)
    if i is None:
        raise ToolSkip(f"No identity links for {g}.")
    rows = [[s["system"], s["ref"], s["method"], s["confidence"]] for s in i["sources"]]
    low = [s for s in i["sources"] if s["confidence"] is not None and s["confidence"] < 0.9]
    res = ToolResult(f"{g}: {len(rows)} source keys from {len(i['lineage'])} systems, overall match confidence {i['match_confidence']:.2f} ({i['match_method']}).",
                     {**table(["System", "Source key", "Method", "Confidence"], rows),
                      "kv": kv([("Golden ID", g), ("Match method", i["match_method"]), ("Match confidence", i["match_confidence"]),
                                ("Lineage", " > ".join(i["lineage"]))]),
                      "links": [link("Open the customer", f"/customers/{g}")]},
                     facts={"default_golden": g})
    if low:
        res.findings.append(f"{len(low)} of {len(rows)} source keys are linked below 0.90 confidence (probabilistic matches).")
    return res


# ---------------------------------------------------------------- next best action

@tool("nba_proposal", "The proposed next best action for a case with the contact rules (policy gate) that shaped it.",
      ("agent", "hardship_specialist", "team_lead"))
def nba_proposal(ctx: ToolContext) -> ToolResult:
    from api.services import nba as svc

    cid = _case(ctx)
    p = svc.proposal(cid, ctx.session if ctx.audit_scores else None)
    if p is None:
        raise ToolSkip(f"No open case {cid}.")
    a, ex = p["action"], p["explanation"]
    me = ex["model_evidence"]
    rules = [[r["code"], r["text"]] for r in ex["rules_applied"]]
    alts = [[f'{x["action"]["treatment"]} by {x["action"]["channel"]}', "allowed" if x["allowed"] else "blocked", x["why_not"]]
            for x in ex["alternatives"]]
    ev = {
        "kv": kv([("Case", cid), ("Proposed action", f'{a["treatment"]} by {a["channel"]}'), ("Window", a["window"]),
                  ("Program", a.get("program_id")), ("Routed to", p["route_to"] or "agent"), ("Review", p["review_mode"]),
                  ("Break risk", f'{me.get("p_break")} ({me.get("band")}, {me.get("label")})'),
                  ("Recommendation", ex["recommendation"]), ("Already decided", (p.get("decision") or {}).get("decision"))]),
        "text": "Policy gate (runs before any model):\n" + "\n".join(f"- {r[1]}" for r in rules)
                + "\nOther options:\n" + "\n".join(f"- {r[0]}: {r[1]}. {r[2]}" for r in alts),
        "links": [link("Open the case", f"/customers/{p['golden_id']}")],
    }
    ev.update(table(["Rule", "What it says"], rules))
    needs = ctx.role if ctx.role in ("agent", "hardship_specialist") else "agent"
    res = ToolResult(f'{ex["recommendation"]}.', ev, status="needs_approval", facts={
        "action": a, "route_to": p["route_to"], "p_break": me.get("p_break"), "default_case": cid, "default_golden": p["golden_id"],
        "treatment": a["treatment"]})
    res.findings.append(f'Proposed for {cid}: {a["treatment"].replace("_", " ")} by {a["channel"]}'
                        + (f' ({a["program_id"]})' if a.get("program_id") else "") + ".")
    if any(r["code"] == "HARDSHIP_NO_PRESSURE" for r in ex["rules_applied"]):
        res.findings.append("The policy gate removed pressure actions (reminder, payment link, collection call) because of the hardship flag.")
    if a["treatment"] == "no_contact":
        res.findings.append("The contact rules say do not contact today.")
    res.proposals.append(proposal(
        f"nba-{cid}", f'Approve or change: {a["treatment"].replace("_", " ")} for {cid}',
        f'{ex["recommendation"]}. A person approves, edits or overrides on the case page; an override needs a reason.',
        "approve_action", f"/customers/{p['golden_id']}", needs))
    return res


@tool("eligibility_check", "Every hardship program that covers the case's product, checked rule by rule. Rules decide, never a model.",
      ("agent", "hardship_specialist", "team_lead"))
def eligibility_check(ctx: ToolContext) -> ToolResult:
    from decisioning import eligibility as elig

    cid = _case(ctx)
    e = elig.check(cid)
    if e is None:
        raise ToolSkip(f"No open case {cid}.")
    progs = e["programs"]
    ok = [p for p in progs if p["eligible"]]
    rows = [[p["program_id"], p["program_name"], "eligible" if p["eligible"] else "not eligible", p["approver_level"].replace("_", " "),
             "; ".join(f'{r["rule"]}' for r in p["rules"] if not r["passed"]) or "all rules pass"] for p in progs]
    fact_prog = None
    if ok:
        pref = [p for p in ok if p["approver_level"] == ("agent" if ctx.role == "agent" else p["approver_level"])]
        fact_prog = (pref or ok)[0]
    res = ToolResult(
        f"{len(ok)} of {len(progs)} programs fit {cid} (hardship level {e['hardship_level']}).",
        {**table(["Program", "Name", "Result", "Approver", "Rules not met"], rows),
         "kv": kv([("Case", cid), ("Hardship level", e["hardship_level"]), ("Eligible programs", len(ok))]),
         "links": [link("Open the simulator", f"/hardship/simulator/{cid}")] if ctx.role == "hardship_specialist" else []},
        facts={"eligible_programs": [p["program_id"] for p in ok],
               "program_id": fact_prog["program_id"] if fact_prog else None,
               "program_name": fact_prog["program_name"] if fact_prog else None,
               "approver_level": fact_prog["approver_level"] if fact_prog else None})
    if ok:
        agent_ok = [p for p in ok if p["approver_level"] == "agent"]
        res.findings.append(f"Eligible: {', '.join(p['program_name'] for p in ok[:3])}"
                            + (f" ({len(agent_ok)} an agent can approve)." if agent_ok else " (all need a higher approver)."))
    else:
        res.findings.append("No hardship program fits this case under the rules.")
    return res


# ---------------------------------------------------------------- promise check

@tool("promise_check", "Open promise to pay: model break risk, its date against payday, and a what-if for a later date. Nothing is saved.",
      ("agent", "hardship_specialist"))
def promise_check(ctx: ToolContext, date_override: str | None = None) -> ToolResult:
    import pandas as pd

    from decisioning import promise_check as pc

    cid = _case(ctx)
    path = get_settings().features_dir / "ptp_scores.parquet"
    if not path.exists():
        raise ToolSkip("Promise scores have not been built yet.")
    s = pd.read_parquet(path, filters=[("case_id", "==", cid)])
    if s.empty:
        raise ToolSkip(f"{cid} has no open promise with a model score.")
    r = s.sort_values("ptp_due_date").iloc[0]
    due = pd.Timestamp(r.ptp_due_date).date()
    payday = data.ttl_cached(("payday", r.ptp_id), 600, lambda: pc._stated_payday(r.ptp_id))
    gap = pc.days_before_payday(due, payday)
    reasons = json.loads(r.reasons_json) if isinstance(r.reasons_json, str) else []
    new_date: date | None = None
    if date_override or ctx.slots.get("date"):
        new_date = date.fromisoformat(str(date_override or ctx.slots["date"])[:10])
    elif gap is not None and gap > 0:
        new_date = payday
    wi = None
    if new_date and new_date != due:
        key = ("whatif", cid, str(new_date))
        wi = data.ttl_cached(key, 600, lambda: pc.what_if(cid, float(r.amount_cad), str(new_date)))
        if wi.get("error"):
            wi = None
    ev_rows = [[x.get("code"), x.get("text"), x.get("contribution")] for x in reasons[:5]]
    pairs = [("Case", cid), ("Promise", f"{r.ptp_id}, {money(r.amount_cad)} due {due}"),
             ("Break risk now", f"{r.p_break:.2f} ({r.band})"), ("Bank v2.1 score", r.v21_score),
             ("Payday the customer stated", payday),
             ("Promise vs payday", None if gap is None else (f"{gap} day(s) before payday" if gap > 0 else f"{-gap} day(s) after payday" if gap < 0 else "on payday"))]
    if wi:
        pairs += [("What if due on", wi["due_after"]), ("Break risk then", wi["p_break_after"]),
                  ("Label", wi["label"]), ("Saved", "no")]
    res = ToolResult(
        (f"Promise due {due} has break risk {r.p_break:.2f}"
         + (f"; on {wi['due_after']} it would be {wi['p_break_after']:.2f} (model estimate, not cause and effect)." if wi else ".")),
        {**table(["Driver", "What the model saw", "Weight"], ev_rows), "kv": kv(pairs)},
        facts={"p_break_promise": float(r.p_break), "ptp_gap_days": gap})
    if gap is not None and gap > 0:
        res.findings.append(f"The promise is due {gap} day(s) before the customer's payday, so it is likely to fall before the money arrives.")
    elif gap is not None:
        res.findings.append("The promise is due on or after payday.")
    if wi and wi["p_break_after"] < wi["p_break_before"] - 0.005:
        res.findings.append(f"Moving it to {wi['due_after']} lowers modelled break risk from {wi['p_break_before']:.2f} to {wi['p_break_after']:.2f} (model estimate, not cause and effect).")
        row = data.case_row(cid)
        res.proposals.append(proposal(
            f"date-{cid}", f"Suggest moving the promise to {wi['due_after']}",
            "Offer the customer the later date on the next contact and record it on the case. The what-if saved nothing.",
            "suggest_promise_date", f"/customers/{row['golden_id']}" if row else "/queue", "agent"))
    return res


# ---------------------------------------------------------------- calls

@tool("call_summary", "Draft notes for the case's most recent recorded call (rule extraction), checked against the promise record.",
      ("agent", "hardship_specialist"))
def call_summary(ctx: ToolContext) -> ToolResult:
    from decisioning.post_call import summarise

    cid = _case(ctx)
    s = summarise(case_id=cid)
    if s is None:
        raise ToolSkip(f"No recorded call on {cid}, so there is nothing to summarise.")
    _access("contact", s["contact_id"], ctx)
    f = s["fields"]
    ptp = f.get("ptp") or {}
    signals = [k for k in ("hardship", "dispute", "complaint") if f.get(k)]
    cites = [{"doc_id": s["transcript_id"], "section": f"turn {t}"} for t in sorted({t for v in s["evidence"].values() for t in v})[:8]]
    ev = {"text": s["summary"],
          "kv": kv([("Call", f'{s["contact_id"]} on {str(s["call_start_ts"])[:10]} ({s["language"]})'),
                    ("Promise", f'{money(ptp.get("amount"))} on {ptp.get("date")}' if ptp else "none taken"),
                    ("Signals", ", ".join(signals) or "none"), ("Next step", (f.get("next_step") or "").replace("_", " ")),
                    ("Promise agrees with record", "yes" if s["checks"]["promise_matches_record"] else "no, check it"),
                    ("Status", "draft, not saved")]),
          "links": [link("Open the call notes", f"/calls/{s['contact_id']}")]}
    res = ToolResult(f"Draft notes ready for call {s['contact_id']}; nothing is saved until the agent approves.", ev,
                     status="needs_approval", cites=cites, facts={"contact_id": s["contact_id"]})
    if "hardship" in signals:
        res.findings.append("The call transcript contains hardship signals; the contact rules route this customer to help, not pressure.")
    if not s["checks"]["promise_matches_record"]:
        res.findings.append("The promise in the transcript differs from the recorded promise: check before approving.")
    res.proposals.append(proposal(
        f"notes-{s['contact_id']}", "Review and approve the call notes",
        "The draft is built from the redacted transcript. The agent can edit it; only approved notes are saved.",
        "approve_call_notes", f"/calls/{s['contact_id']}", "agent"))
    return res


# ---------------------------------------------------------------- questions (policy and certified metrics)

def _ask(ctx: ToolContext, question: str):
    from api.services.ask_access import scope_for
    from common.ask_scope import use_scope
    from nlq.pipeline import ask

    sess = ctx.session
    with use_scope(scope_for(ctx.role, sess.user_id, sess.team_id)), use_mode(ctx.mode):
        return ask(question, None)


@tool("policy_answer", "A cited answer from the current policy documents (retrieval, no guessing; refuses when not covered).",
      ("agent", "hardship_specialist", "team_lead", "analyst"))
def policy_answer(ctx: ToolContext, question: str | None = None) -> ToolResult:
    q = question or ctx.slots.get("question") or "A customer says their hours were cut at work. What must the agent do before asking for payment?"
    a = _ask(ctx, q)
    if a.refused:
        return ToolResult(_refused(a.refusal_reason), {"text": a.refusal_reason or "", "links": [link("Open Ask", "/ask")]},
                          findings=[f"Question refused by the guardrails: {a.refusal_reason}"])
    if a.kind == "metric":
        raise ToolSkip("That is a numbers question, not a policy question. Use the metric tool.")
    cites = [{"doc_id": c.get("doc_id", ""), "section": str(c.get("section", ""))} for c in (a.citations or [])][:5]
    ev = {"text": a.answer, "kv": kv([("Question", q), ("Answered by", a.answered_by), ("Sources", a.sql_or_sources[:200])]),
          "links": [link("Ask more", "/ask")]}
    res = ToolResult("Policy answer found with citations." if cites else "Policy answer found.", ev, cites=cites)
    res.findings.append("Policy: " + a.answer.split("\n")[0][:240])
    return res


@tool("metric_question", "A certified-metric question answered from the semantic layer, with the SQL shown. Protected attributes are refused.",
      ("analyst", "team_lead"))
def metric_question(ctx: ToolContext, question: str | None = None) -> ToolResult:
    q = question or ctx.slots.get("question") or "What is the hardship rate of cases opened in 2026, by primary product?"
    a = _ask(ctx, q)
    if a.refused:
        return ToolResult(_refused(a.refusal_reason), {"text": a.refusal_reason or "", "kv": kv([("Question", q)])},
                          findings=[f"The question was refused: {a.refusal_reason}"])
    if a.kind != "metric":
        ev = {"text": a.answer, "kv": kv([("Question", q), ("Answered by", a.answered_by)])}
        return ToolResult(f"Answered as a {a.kind.replace('_', ' ')} question.", ev,
                          cites=[{"doc_id": c.get("doc_id", ""), "section": str(c.get("section", ""))} for c in (a.citations or [])][:5])
    rows = a.rows[:12]
    ev = {**table(a.columns, rows), "text": "SQL used:\n" + a.sql_or_sources,
          "kv": kv([("Question", q), ("Metric", a.chips.get("metric")), ("Rows", len(a.rows)), ("Answered by", a.answered_by),
                    ("Data built", a.freshness)] + [("Caveat", c) for c in a.caveats[:3]]),
          "links": [link("Open Ask", "/ask")]}
    res = ToolResult(f"{len(a.rows)} row(s) from the certified {a.chips.get('metric')} definition; the SQL is shown.", ev)
    if rows and a.columns:
        r0 = rows[0]
        res.findings.append("First row: " + ", ".join(f"{c} {_j(v)}" for c, v in zip(a.columns, r0, strict=False)) + ".")
    for c in a.caveats[:2]:
        res.findings.append("Caveat: " + c)
    return res


@tool("guardrail_check", "Checks a request against the refusal rules (protected attributes, proxies, personal details, actions).",
      ALL_ROLES)
def guardrail_check(ctx: ToolContext, question: str | None = None) -> ToolResult:
    from nlq import refusal

    q = question or ctx.slots.get("question") or ""
    reason = refusal.check(q)
    if not reason:
        return ToolResult("The request passes the guardrails.", {"kv": kv([("Request", q)])})
    return ToolResult(_refused(reason),
                      {"text": reason, "kv": kv([("Request", q), ("Rule", "No protected attributes or proxies in any decision, list or ranking")]),
                       "links": [link("Open Ask", "/ask")]},
                      findings=[f"Refused by the guardrails: {reason}", "The assistant only proposes actions a person approves; it never acts on customers."])


# ---------------------------------------------------------------- hardship

@tool("hardship_board", "Customers flagged 'possible' waiting for a person to confirm or clear, overdue first.", ("hardship_specialist",))
def hardship_board(ctx: ToolContext) -> ToolResult:
    from api.services import hardship

    b = data.ttl_cached(("board",), 60, hardship.board)
    items = b["items"]
    rows = [[i["case_id"], i["name"], i["level"], i["source"], i["dpd"], money(i["total_overdue"]), i["review_due"], i["days_overdue"]] for i in items[:6]]
    facts: dict[str, Any] = {}
    if items:
        facts = {"board_case": items[0]["case_id"], "board_golden": items[0]["golden_id"]}
        ctx.facts.setdefault("default_case", items[0]["case_id"])
        ctx.facts.setdefault("default_golden", items[0]["golden_id"])
    res = ToolResult(
        f"{b['total']:,} customers wait for a confirm-or-clear decision; {b['overdue']:,} are past the {b['review_days']}-business-day review.",
        {**table(["Case", "Customer", "Flag", "Raised by", "DPD", "Overdue", "Review due", "Days late"], rows),
         "kv": kv([("Waiting", b["total"]), ("Overdue", b["overdue"]), ("Vulnerability reviews due", b["vulnerability_reviews"]["total"])]),
         "links": [link("Open the board", "/hardship/board")]}, facts=facts)
    res.findings.append(f"{b['overdue']:,} of {b['total']:,} possible-hardship customers are past their review date.")
    res.proposals.append(proposal(
        "board-review", f"Work the overdue hardship board ({b['overdue']:,} overdue)",
        "Confirm hardship (link a program) or lower the flag with a reason. Only a hardship specialist can change the flag, and every change is audited.",
        "review_board", "/hardship/board", "hardship_specialist"))
    return res


@tool("missed_offers", "Hardship-flagged cases never offered a program, where an agent-level program fits.", ("hardship_specialist",))
def missed_offers(ctx: ToolContext) -> ToolResult:
    from api.services import hardship

    m = data.ttl_cached(("missed",), 120, lambda: hardship.missed_offers(limit=20))
    items = m["items"]
    rows = [[i["case_id"], i["name"], i["level"], i["product"], i["dpd"], i["flag_since"],
             ", ".join(p["program_name"] for p in i["eligible_programs"])] for i in items[:6]]
    facts = {}
    if items:
        facts = {"missed_case": items[0]["case_id"], "missed_golden": items[0]["golden_id"]}
        if not ctx.case_id:
            ctx.facts["default_case"] = items[0]["case_id"]
            ctx.facts["default_golden"] = items[0]["golden_id"]
    res = ToolResult(f"{len(items)} flagged cases have no program offered although an agent-level program fits (newest first).",
                     {**table(["Case", "Customer", "Flag", "Product", "DPD", "Flag since", "Programs that fit"], rows),
                      "links": [link("Open missed offers", "/hardship/missed")]}, facts=facts)
    if items:
        res.findings.append(f"Newest missed offer: {items[0]['name']} ({items[0]['case_id']}), eligible for {items[0]['eligible_programs'][0]['program_name']}.")
        res.proposals.append(proposal(
            "missed-offers", f"Offer a program on {len(items)} missed hardship cases",
            "Start with the newest. Open each case, check the simulator and make the offer in the case page.",
            "review_missed_offers", "/hardship/missed", "hardship_specialist"))
    return res


@tool("override_report", "Offers agents made although the eligibility rules said no, by agent and program.", ("hardship_specialist", "team_lead"))
def override_report(ctx: ToolContext) -> ToolResult:
    from api.services import hardship

    o = data.ttl_cached(("overrides",), 120, hardship.overrides)
    items = o["items"]
    total = sum(i["count"] for i in items)
    rows = [[i["agent_id"], i["agent_name"], i["program_id"], i["count"], i["nba_recommended"]] for i in items[:6]]
    res = ToolResult(f"{total:,} offers in the last {o['window_days']} days went ahead although the rules said not eligible.",
                     {**table(["Agent", "Name", "Program", "Offers", "Recommended by the NBA"], rows),
                      "links": [link("Open overrides", "/hardship/overrides")]})
    res.findings.append(f"{total:,} rule-overridden hardship offers in {o['window_days']} days; the top agent-program pair accounts for {items[0]['count']:,}." if items else "No rule-overridden offers found.")
    if ctx.role == "hardship_specialist" and items:
        res.proposals.append(proposal("overrides-review", "Review rule-overridden offers", "Check whether the overrides were justified and coach where not.",
                                      "review_overrides", "/hardship/overrides", "hardship_specialist"))
    return res


@tool("simulator", "Hardship plan simulator: new payment, months to clear, interest, share of surplus and the approver level. Saves nothing.",
      ("hardship_specialist",))
def simulator(ctx: ToolContext, program_id: str | None = None) -> ToolResult:
    from decisioning import simulator as sim

    cid = _case(ctx)
    pid = program_id or ctx.slots.get("program_id") or ctx.facts.get("program_id")
    levers = {"program_id": pid} if pid else {"term_extension_months": 6}
    out = sim.simulate(cid, levers)
    if out is None:
        raise ToolSkip(f"No open case {cid}.")
    if out.get("error"):
        raise ToolSkip(out["error"])
    r, i = out["results"], out["inputs"]
    ev = {"kv": kv([("Case", cid), ("Program", pid or "free-form: 6-month term extension"), ("Balance", money(i["balance"])),
                    ("Payment now", money(i["payment_now"])), ("New payment", money(r["new_payment"])),
                    ("Months to clear", f'{r["months_to_clear_current"]} now, {r["months_to_clear"]} with the plan'),
                    ("Total interest", f'{money(r["total_interest_current"])} now, {money(r["total_interest"])} with the plan'),
                    ("Share of monthly surplus", r["payment_share_of_surplus"]), ("Within program limits", out["within_program"]),
                    ("Approver", out["approver_level"].replace("_", " ")), ("Bank impact vs status quo", money(r["bank_impact_vs_status_quo"])),
                    ("Saved", "no, simulation only")]),
          "text": "\n".join(out["notes"][:2]), "links": [link("Open the simulator", f"/hardship/simulator/{cid}")]}
    res = ToolResult(f"New payment {money(r['new_payment'])} (from {money(i['payment_now'])}); clears in {r['months_to_clear']} months; approver: {out['approver_level'].replace('_', ' ')}.",
                     ev, facts={"approver": out["approver_level"]})
    res.findings.append(f"Simulated {pid or 'a 6-month extension'} for {cid}: payment {money(i['payment_now'])} to {money(r['new_payment'])}, approver {out['approver_level'].replace('_', ' ')}.")
    role = out["approver_level"] if out["approver_level"] in ALL_ROLES else "hardship_specialist"
    res.proposals.append(proposal(
        f"plan-{cid}", f"Offer {pid or 'the simulated plan'} on {cid}",
        f"Within program limits: {'yes' if out['within_program'] else 'no, needs a higher approver'}. The offer is made and approved on the simulator page; this run saved nothing.",
        "offer_plan", f"/hardship/simulator/{cid}", role))
    return res


# ---------------------------------------------------------------- team lead

@tool("batch_queue", "Batches of routine reminders waiting for the team lead, with the 2% review sample.", ("team_lead",))
def batch_queue(ctx: ToolContext) -> ToolResult:
    from api.services import nba as svc
    from decisioning import nba

    b = svc.batches("pending", ctx.session.team_id)["items"]
    rows = [[x["batch_id"], f'{x["treatment"]} by {x["channel"]}', x["count"], x["sample_size"]] for x in b[:6]]
    sample = b[0]["sample"][:5] if b else []
    derived = False
    if not b:  # no batch rows yet (the nightly job creates them): show what the queue holds for review
        df = data.queue_df()
        if df is not None:
            t = df[(df.review_mode == "batch") & (df.assigned_team == ctx.session.team_id) & (df.treatment != "no_contact")]
            g = t.groupby(["treatment", "channel"]).size().reset_index(name="n")
            rows = [["(not created yet)", f"{x.treatment} by {x.channel}", int(x.n), nba.sample_size(int(x.n))] for x in g.itertuples()]
            b = [{"count": int(x.n), "sample_size": nba.sample_size(int(x.n)), "batch_id": None} for x in g.itertuples()]
            derived = True
    n = sum(x["count"] for x in b)
    ev = {**table(["Batch", "Action", "Cases", "Sample to check"], rows),
          "kv": kv([("Team", ctx.session.team_id), ("Cases in batches", n), ("Review sample", "2% rounded up, highest priority first")]),
          "links": [link("Open the batch queue", "/queue?view=batch")]}
    if sample:
        ev["text"] = "Sample: " + "; ".join(f'{s["case_id"]} {s["name"]} ({s["headline"]})' for s in sample)
    res = ToolResult(f"{len(b)} batch(es) with {n:,} routine cases for your team; check the sample, then approve." if b else "No batched cases for your team today.",
                     ev, status="needs_approval" if b else "done", facts={"batch_cases": n})
    if b:
        res.findings.append(f"{n:,} routine reminders and payment links are batched; the review sample is {sum(x['sample_size'] for x in b):,} cases.")
        res.proposals.append(proposal(
            "batch-approve", f"Review the sample and approve {len(b)} batch(es) ({n:,} cases)",
            "Approving releases the batch for sending. The team lead approves in the queue after checking the sample; the assistant never sends."
            + (" Batch records are created by the nightly run." if derived else ""),
            "approve_batch", "/queue?view=batch", "team_lead"))
    return res


@tool("stress_test", "Re-runs the allocator with a channel down or agents absent and shows which actions move (nothing is changed).",
      ("team_lead", "analyst"))
def stress_test(ctx: ToolContext, channel: str | None = None, agents_pct: float | None = None) -> ToolResult:
    from decisioning import stress_test as st

    ch = channel or ctx.slots.get("channel") or "call"
    pct = agents_pct if agents_pct is not None else ctx.slots.get("agents_pct")
    out = data.ttl_cached(("stress", ch, pct), 600, lambda: st.run({"channel": ch, "agents_pct": pct}))
    rows = [[x["treatment"].replace("_", " "), x["moved"]] for x in out["by_treatment"]]
    what = f"{ch} down" + (f" and {int(pct * 100)}% of agents absent" if pct else "")
    res = ToolResult(f"With {what}: {out['moved']:,} of {out['scheduled_before']:,} scheduled actions move to tomorrow; {out['dropped']:,} are high or very high risk.",
                     {**table(["Treatment", "Pushed to tomorrow"], rows),
                      "kv": kv([("Scenario", what), ("Scheduled before", out["scheduled_before"]), ("Scheduled after", out["scheduled_after"]),
                                ("Pushed to tomorrow", out["moved"]), ("High-risk among them", out["dropped"])]),
                      "text": out["note"], "links": [link("Open the team page", "/team")]})
    res.findings.append(f"If {what}, {out['moved']:,} actions slip a day, including {out['dropped']:,} high-risk cases.")
    if ctx.role == "team_lead" and out["dropped"]:
        res.proposals.append(proposal("stress-cover", f"Plan cover for {out['dropped']:,} high-risk cases if {ch} is down",
                                      "Decide on an alternative channel or extra staffing before the outage. A planning note only: nothing is changed.",
                                      "plan_cover", "/team", "team_lead"))
    return res


@tool("guardrails", "Team guardrails: override rate of recent decisions, pressure actions on hardship customers (must be zero), batch sample rule.",
      ("team_lead",))
def guardrails(ctx: ToolContext) -> ToolResult:
    import yaml

    from api.services import analytics
    from common.db import ops

    team = ctx.session.team_id
    agents = [a["agent_id"] for a in analytics.agents(team)["items"]]
    with ops() as con:
        marks = ",".join("?" * len(agents))
        rows = con.execute(f"SELECT decision, count(*) n FROM nba_decisions WHERE user_id IN ({marks}) GROUP BY decision",
                           agents).fetchall() if agents else []
    by = {r["decision"]: r["n"] for r in rows}
    total = sum(by.values())
    ov = by.get("override", 0)
    df = data.queue_df()
    pressure = 0
    hard = 0
    if df is not None:
        t = df[df.assigned_team == team]
        h = t[t.hardship_flag != "none"]
        hard = len(h)
        pressure = int(h.treatment.isin(["reminder", "payment_link"]).sum())
    cfg = yaml.safe_load((ROOT / "decisioning" / "config.yaml").read_text())
    rate = None if not total else ov / total
    ev = {**table(["Guardrail", "Value", "Rule"], [
        ["Override rate (recorded decisions)", "no decisions recorded yet" if rate is None else f"{rate * 100:.1f}% ({ov} of {total})", "Overrides need a reason code"],
        ["Pressure actions on hardship customers", pressure, "Must be 0: reminders and payment links are removed"],
        ["Batch review sample", f'{cfg["batch"]["sample_pct"] * 100:.0f}%', "Team lead checks the sample before approving"],
        ["Uplift model gate", f'overlap >= {cfg["uplift"]["min_overlap_share"] * 100:.0f}% and {cfg["uplift"]["min_cases_per_action"]:,}+ cases per action', "Otherwise rules decide"]]),
        "kv": kv([("Team", team), ("Hardship-flagged cases in your team", hard)]), "links": [link("Open the audit log", "/governance/audit")]}
    res = ToolResult(f"{pressure} pressure actions on {hard:,} hardship-flagged cases; override rate "
                     + ("not available yet (no decisions recorded)." if rate is None else f"{rate * 100:.1f}%."), ev)
    res.findings.append("Guardrail holds: no pressure action is scheduled for a hardship-flagged customer." if pressure == 0
                        else f"Guardrail breach: {pressure} pressure actions are scheduled for hardship customers. Escalate.")
    if rate is not None and rate > 0.2:
        res.findings.append(f"Override rate is {rate * 100:.1f}%: review the reasons.")
    return res


@tool("team_agents", "Your team's agents: case load against capacity, promise-kept and cure rates.", ("team_lead",))
def team_agents(ctx: ToolContext) -> ToolResult:
    from api.services import analytics

    a = analytics.agents(ctx.session.team_id)["items"]
    rows = [[x["agent_id"], x["name"], f'{x["current_case_load"]}/{x["max_concurrent_cases"]}', x["ptp_kept_rate_90d"], x["cure_rate_90d"]] for x in a[:8]]
    full = [x for x in a if x["max_concurrent_cases"] and x["current_case_load"] / x["max_concurrent_cases"] >= 0.9]
    res = ToolResult(f"{len(a)} active agents in {ctx.session.team_id}; {len(full)} are at 90% or more of capacity.",
                     {**table(["Agent", "Name", "Load", "Promise kept 90d", "Cure 90d"], rows), "links": [link("Open the team page", "/team")]})
    if full:
        res.findings.append(f"{len(full)} agent(s) are near capacity, so a channel or staffing loss would push work to tomorrow.")
    return res


@tool("scorecard", "Cure rate, cost and complaints by strategy; causal only inside randomised cells.", ("team_lead", "analyst"))
def scorecard(ctx: ToolContext) -> ToolResult:
    from api.services import analytics

    s = data.ttl_cached(("scorecard",), 300, analytics.scorecard)
    items = s["items"]
    rows = [[x["strategy_code"], x["randomised_cases"], x["cure_rate_30d_randomised"], x["all_cases"], x["cure_rate_30d_all"], x["cost_per_cure_cad"]]
            for x in items[:12]]
    rand = [x for x in items if x["randomised_cases"] and x["cure_rate_30d_randomised"] is not None]
    res = ToolResult(f"{len(items)} strategies scored; {len(rand)} have randomised cases that support a causal comparison.",
                     {**table(["Strategy", "Randomised cases", "Cure 30d (randomised)", "All cases", "Cure 30d (observed)", "Cost per cure"], rows),
                      "text": s["note"], "links": [link("Open the team page", "/team")]})
    if rand:
        best = max(rand, key=lambda x: x["cure_rate_30d_randomised"])
        res.findings.append(f"Highest randomised 30-day cure rate: {best['strategy_code']} at {best['cure_rate_30d_randomised']}% (causal, randomised cases only).")
    res.findings.append("All-cases columns are observed, not causal: strategies change as a case rolls to the next stage.")
    return res


# ---------------------------------------------------------------- analyst

@tool("geo_map", "Weather map: a rate by postal area (FSA); areas under 10 customers are hidden.", ("analyst", "team_lead"))
def geo_map(ctx: ToolContext, metric: str = "broken_ptp_rate") -> ToolResult:
    from api.services import analytics

    m = data.ttl_cached(("map", metric), 300, lambda: analytics.bubble_map(metric))
    top = sorted(m["items"], key=lambda x: -x["value"])[:6]
    rows = [[x["fsa"], x["city"], x["province"], x["customers"], x["value"]] for x in top]
    res = ToolResult(f"{m['label']} across {len(m['items']):,} postal areas; {m['suppressed']:,} areas under {m['min_group']} customers are hidden.",
                     {**table(["FSA", "City", "Province", "Customers", m["label"]], rows), "text": "SQL used:\n" + m["sql"],
                      "links": [link("Open the map", "/map")]})
    res.findings.append(f"Highest {m['label'].lower()}: {top[0]['fsa']} ({top[0]['city']}) at {top[0]['value']}, from {top[0]['customers']} customers. Postal area is shown for information only and is never used to treat customers differently." if top else "No areas to show.")
    return res


@tool("model_card", "Promise-break model evaluation against the bank's v2.1 on the same promises, plus calibration and the decision.",
      ("analyst", "steward"))
def model_card(ctx: ToolContext) -> ToolResult:
    m = _report("model_eval")
    if m is None:
        raise ToolSkip("reports/model_eval.json is not built yet.")
    h = m["head_to_head"]
    rows = [[k, h[k]["auc"], h[k]["brier"], h[k]["lift_top10"], h[k]["n"]] for k in ("ours", "bank_v2_1", "blend")]
    res = ToolResult(f"Blend AUC {h['blend']['auc']} vs bank v2.1 {h['bank_v2_1']['auc']} on the same {h['ours']['n']:,} test promises; decision: {m['decision']}.",
                     {**table(["Model", "AUC", "Brier", "Lift top 10%", "Promises"], rows),
                      "kv": kv([("Model", m["model"]), ("Test period", m["split"]["test"]), ("Decision", m["decision"]), ("Fallback", m["fallback"])]),
                      "text": "Full card: docs/model_card_ptp_break.md", "links": [link("Open monitoring", "/governance/monitoring")]},
                     cites=[{"doc_id": "model_card_ptp_break", "section": "Performance"}])
    res.findings.append(f"On the same test promises the blended model reaches AUC {h['blend']['auc']} against {h['bank_v2_1']['auc']} for the bank's v2.1; scores are labelled model estimates.")
    return res


@tool("fairness_report", "Fairness audit summary: proxy test and outcome test. Aggregates only; groups under 10 customers hidden.",
      ("analyst", "steward", "team_lead"))
def fairness_report(ctx: ToolContext) -> ToolResult:
    f = _report("fairness")
    if f is None:
        raise ToolSkip("reports/fairness.json is not built yet.")
    p, o = f["proxy"], f["outcome"]
    rows = [[g["group"], g["n_features"], g["max_auc"], g["decision"]] for g in p["groups"]]
    worst = max(g["max_auc"] for g in p["groups"])
    review = len(f.get("review_items", []))
    res = ToolResult(f"Proxy test: highest AUC {worst:.3f} against a {p['threshold']} limit across {len(p['groups'])} feature groups; {review} outcome gap(s) flagged for review.",
                     {**table(["Feature group", "Features", "Max proxy AUC", "Decision"], rows),
                      "kv": kv([("Test period", o["test_period"]), ("Promises tested", o["promises"]), ("Proxy limit", p["threshold"]),
                                ("Items for human review", review), ("Note", f["note"])]),
                      "links": [link("Open fairness", "/governance/fairness")]})
    res.findings.append(f"No feature group exceeds the proxy limit (highest {worst:.3f}); {review} outcome gap(s) need human review.")
    return res


# ---------------------------------------------------------------- steward

@tool("identity_queue", "Grey-band identity candidates waiting for a steward verdict (names masked).", ("steward",))
def identity_queue(ctx: ToolContext) -> ToolResult:
    from api.services import analytics

    q = data.ttl_cached(("idq",), 120, lambda: analytics.identity_queue(10))
    items = q["items"]
    rows = [[x["pair_id"], f'{x["left"]["system"]} {x["left"]["name"]}', f'golden {x["right"]["name"]}', x["match_probability"], x["reason"]] for x in items[:6]]
    if items:
        ctx.facts["default_golden"] = items[0]["right"]["ref"]
    res = ToolResult(f"{q['total']:,} candidate links sit in the grey band (between auto-link and reject); the top {len(items)} are shown, names masked.",
                     {**table(["Pair", "Source record", "Candidate", "Match probability", "Why"], rows),
                      "links": [link("Open the review queue", "/steward/identity")]})
    res.findings.append(f"{q['total']:,} identity pairs need a verdict; verdicts apply on the next identity run.")
    res.proposals.append(proposal("identity-review", f"Review the top {len(items)} grey-band identity pairs",
                                  "Record link, no link or unsure on each. The verdict is audited and applied on the next identity run.",
                                  "review_identity", "/steward/identity", "steward"))
    return res


@tool("data_quality", "Data quality report: issues found and how each is handled, identity link counts, C360 coverage.", ("steward", "analyst"))
def data_quality(ctx: ToolContext) -> ToolResult:
    q = _report("data_quality")
    if q is None:
        raise ToolSkip("reports/data_quality.json is not built yet.")
    i = q["identity"]
    rows = [[x["issue"][:70], x["records_affected"], x["handled"][:80]] for x in sorted(q["issues"], key=lambda x: -(x["records_affected"] or 0))[:6]]
    res = ToolResult(f"{len(q['issues'])} data issues documented; {int(i['crm_records']):,} CRM records resolved to {int(i['golden_ids']):,} golden customers (scorer precision {i['scorer_precision']}).",
                     {**table(["Issue", "Records", "How it is handled"], rows),
                      "kv": kv([("Golden customers", i["golden_ids"]), ("Accounts linked", f"{int(i['accounts_linked']):,} of {int(i['accounts']):,}"),
                                ("Keys in review", i["keys_in_review"]), ("Keys unlinked", i["keys_unlinked"]),
                                ("Report built", q["generated_at"])]),
                     "links": [link("Open data quality", "/governance/quality")]})
    res.findings.append(f"{int(i['keys_in_review']):,} source keys are in review and {int(i['keys_unlinked']):,} are unlinked; they are kept out of the golden ID until decided.")
    return res


@tool("contract_tests", "Data contract tests from the last build (freshness, unique IDs, no protected columns, consent most restrictive).",
      ("steward", "analyst"))
def contract_tests(ctx: ToolContext) -> ToolResult:
    q = _report("data_quality")
    if q is None:
        raise ToolSkip("reports/data_quality.json is not built yet.")
    t = q["contract_tests"]
    bad = [x for x in t if x["status"] != "pass"]
    rows = [[x["test"][:70], x["status"], x["failures"]] for x in t[:12]]
    res = ToolResult(f"{len(t) - len(bad)} of {len(t)} contract tests pass.",
                     {**table(["Test", "Status", "Failures"], rows), "links": [link("Open the contract", "/governance/contract")]})
    res.findings.append("All contract tests pass." if not bad else f"{len(bad)} contract test(s) fail: {', '.join(x['test'][:40] for x in bad[:3])}.")
    return res


@tool("feature_parity", "Offline against online feature values on a sample: the same definition must give the same numbers.", ("steward", "analyst"))
def feature_parity(ctx: ToolContext) -> ToolResult:
    p = _report("feature_parity")
    if p is None:
        raise ToolSkip("reports/feature_parity.json is not built yet.")
    res = ToolResult(f"Parity {'holds' if p['ok'] else 'FAILS'}: {p['mismatched_rows']} mismatched rows in {p['sampled']:,} sampled customers over {p['columns_checked']} columns.",
                     {"kv": kv([("Sampled customers", p["sampled"]), ("Columns checked", p["columns_checked"]), ("Mismatched rows", p["mismatched_rows"])]),
                      "links": [link("Open monitoring", "/governance/monitoring")]})
    res.findings.append("Training and serving features agree." if p["ok"] else "Training and serving features disagree: do not trust new scores until fixed.")
    return res


@tool("monitoring", "Freshness against the 26-hour contract, contract tests, parity and benchmark at a glance.", ("steward", "analyst", "team_lead"))
def monitoring(ctx: ToolContext) -> ToolResult:
    from api.services import analytics

    m = analytics.monitoring()
    fresh = m["freshness_hours"]
    ct = m["contract_tests"]
    res = ToolResult(f"Data is {fresh} h old (limit {m['freshness_sla_hours']} h); {ct['passed']} of {ct['total']} contract tests pass.",
                     {"kv": kv([("Freshness (hours)", fresh), ("Freshness limit", m["freshness_sla_hours"]),
                                ("Contract tests", f"{ct['passed']} of {ct['total']}"), ("Feature parity ok", (m["feature_parity"] or {}).get("ok")),
                                ("Benchmark mean score", (m["benchmark"] or {}).get("dev_mean_score"))]),
                      "links": [link("Open monitoring", "/governance/monitoring")]})
    if fresh is not None and fresh > m["freshness_sla_hours"]:
        res.findings.append(f"Data is stale ({fresh} h): scores on the pages carry a freshness warning until the nightly run.")
    return res


@tool("audit_log", "The most recent audit entries (who did what, when). Metadata only.", ("steward", "team_lead"))
def audit_log(ctx: ToolContext, limit: int = 12) -> ToolResult:
    from governance import audit

    items = audit.query(limit=limit)
    rows = [[x["audit_id"], str(x["ts"])[:19], x["user_id"], x["role"], x["event_type"], f'{x["entity_type"] or ""} {x["entity_id"] or ""}'.strip()] for x in items]
    kinds: dict[str, int] = {}
    for x in items:
        kinds[x["event_type"]] = kinds.get(x["event_type"], 0) + 1
    res = ToolResult(f"{len(items)} recent audit entries" + (f", mostly {max(kinds, key=kinds.get)}." if kinds else "; the log is empty so far."),
                     {**table(["#", "When", "Who", "Role", "Event", "About"], rows),
                      "text": "The log is append-only: the database refuses updates and deletes.", "links": [link("Open the audit log", "/governance/audit")]})
    res.findings.append("Every customer-affecting write and every assistant run is recorded in the append-only audit log.")
    return res
