# ruff: noqa: E501
"""Runs one assistant request: pick a plan (rules, or a language model limited to the closed list), call the tools,
collect findings and proposals, word the summary and audit the run. The plan and the tools always come from code."""

from __future__ import annotations

import logging
import re
import time
from typing import Any

import jsonschema

from api.schemas.common import Session
from common import llm_mode
from common.config import get_settings
from decisioning.assistant import plans as P
from decisioning.assistant.tools import TOOLS, ToolContext, default_case_for, run_tool
from governance import audit
from llm.providers.offline import register

log = logging.getLogger(__name__)
NUM_RE = re.compile(r"\d+(?:[.,]\d+)*")
CHANNELS = {"call", "sms", "email", "push"}
CASE_TOOLS = {"customer_360", "nba_proposal", "eligibility_check", "promise_check", "call_summary", "simulator"}
PERSONA_LABEL = {"agent": "agent", "hardship_specialist": "hardship specialist", "team_lead": "team lead",
                 "analyst": "analyst", "steward": "data steward"}


# ---------------------------------------------------------------- the model, behind one function (tests replace it)

def _model(task: str, inputs: dict) -> dict:
    from llm.client import complete_json

    return complete_json("assistant_plan", 1, {"task": task, **inputs}, "assistant_plan")


@register("assistant_plan")
def _offline(inputs: dict) -> dict:
    """Offline handler: the same rules the rules mode uses, so the prompt works with LLM_PROVIDER=offline."""
    persona = inputs.get("persona", "")
    if inputs.get("task") == "summary":
        return {"summary": template_summary(inputs.get("persona_label", persona), inputs.get("plan_title", ""),
                                            inputs.get("findings", []), inputs.get("proposals", []), inputs.get("problems", []))}
    goal = inputs.get("goal", "")
    plan, _ = P.match_plan(persona, goal, bool(P.extract_slots(goal).get("case_id")))
    slots = {k: v for k, v in P.extract_slots(goal).items() if k in ("case_id", "golden_id", "date", "amount", "channel", "question")}
    return {"plan_id": plan.id, "slots": slots}


# ---------------------------------------------------------------- what the role may use (decided before any model)

def allowed_tools(persona: str) -> set[str]:
    return {n for n, t in TOOLS.items() if persona in t.roles}


def allowed_plans(persona: str) -> list[P.Plan]:
    """Plans whose every tool the role may use. The model is shown only these."""
    ok = allowed_tools(persona)
    return [p for p in P.plans_for(persona) if all(st.tool in ok for st in p.steps)]


# ---------------------------------------------------------------- validation of model output

def validate_plan_output(out: dict, persona: str, goal: str, extra_text: str = "", session: Session | None = None
                         ) -> tuple[str, dict] | None:
    """The model's pick, or None if it is not acceptable. Only a plan id from the closed list is accepted; a slot is
    kept only when its value appears in the evidence (the goal text and the request fields)."""
    from llm.client import load_schema

    clean = {k: v for k, v in out.items() if k != "_meta"}
    try:
        jsonschema.validate(clean, load_schema("assistant_plan"))
    except jsonschema.ValidationError:
        return None
    pid = clean.get("plan_id")
    if not isinstance(pid, str) or pid not in {p.id for p in allowed_plans(persona)}:
        return None
    # a model that names a tool the role may not use is rejected outright
    named = [clean.get("tool")] + list(clean.get("tools") or [])
    if any(isinstance(t, str) and t not in allowed_tools(persona) for t in named if t):
        return None
    evidence = f"{goal} {extra_text}".lower()
    slots: dict[str, Any] = {}
    for k, v in (clean.get("slots") or {}).items():
        if v is None or v == "":
            continue
        s = str(v).strip()
        if k == "case_id" and P.CASE_RE.fullmatch(s) and s.lower() in evidence:
            slots[k] = s
        elif k == "golden_id" and P.GOLDEN_RE.fullmatch(s) and s.lower() in evidence:
            slots[k] = s
        elif k == "date" and P.DATE_RE.fullmatch(s) and s in evidence:
            slots[k] = s
        elif k == "amount" and isinstance(v, (int, float)) and not isinstance(v, bool) and (f"{v:g}" in evidence or f"{v:,.0f}" in evidence):
            slots[k] = float(v)
        elif k == "channel" and s in CHANNELS and s in evidence or (k == "channel" and s == "call" and "dialer" in evidence):
            slots[k] = s
        elif k == "question" and " ".join(s.lower().split()) in " ".join(evidence.split()):
            slots[k] = s
    if session is not None:  # row-level access, same check the screens use
        from fastapi import HTTPException

        from api import access

        for k, fn in (("case_id", access.case), ("golden_id", access.golden)):
            if k in slots:
                try:
                    fn(session, slots[k])
                except HTTPException:
                    del slots[k]
    return pid, slots


def validate_summary(text: Any, evidence_numbers: set[str]) -> str | None:
    """A model-written summary is accepted only if it is short plain text whose numbers all appear in the evidence."""
    if not isinstance(text, str):
        return None
    t = " ".join(text.split())
    if not t or len(t) > 900:
        return None
    for n in NUM_RE.findall(t):
        if n.replace(",", "").rstrip(".") not in evidence_numbers:
            return None
    return t


def _numbers(*chunks: Any) -> set[str]:
    out: set[str] = set()

    def walk(x: Any) -> None:
        if x is None:
            return
        if isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, (list, tuple)):
            for v in x:
                walk(v)
        else:
            for n in NUM_RE.findall(str(x)):
                out.add(n.replace(",", "").rstrip("."))
                out.add(n.replace(",", "").rstrip(".").split(".")[0])

    for c in chunks:
        walk(c)
    return out


# ---------------------------------------------------------------- deterministic wording

def template_summary(persona_label: str, plan_title: str, findings: list[str], proposals: list[str], problems: list[str]) -> str:
    parts = [f"{plan_title} ({persona_label})."] + [f.rstrip(".") + "." for f in findings[:4]]
    if proposals:
        parts.append(f"{len(proposals)} proposed action(s) wait for a person to approve: " + "; ".join(proposals[:3]) + ".")
    else:
        parts.append("Nothing needs approval from this run.")
    if problems:
        parts.append("Not completed: " + "; ".join(problems[:2]))
    return " ".join(parts)


# ---------------------------------------------------------------- the run

def run(session: Session, goal: str | None = None, case_id: str | None = None, golden_id: str | None = None,
        mode: str | None = None) -> dict:
    t0 = time.perf_counter()
    persona = getattr(session.role, "value", str(session.role))
    goal = (goal or "").strip()[:500]
    notes: list[str] = []
    case_id = case_id if case_id and P.CASE_RE.fullmatch(case_id.strip()) else None
    golden_id = golden_id if golden_id and P.GOLDEN_RE.fullmatch(golden_id.strip()) else None
    rule_slots = P.extract_slots(goal)
    case_id = case_id or rule_slots.get("case_id")
    golden_id = golden_id or rule_slots.get("golden_id")
    request_text = f"{case_id or ''} {golden_id or ''}"

    # which mode runs
    want_model = mode == "llm" or (mode is None and get_settings().llm_provider != "offline")
    mode_note = None
    if mode == "llm":
        av = llm_mode.availability()
        if not av["available"]:
            mode_note = av["reason"] + " Ran with rules instead."
            want_model = False
    elif want_model and not llm_mode.availability()["available"]:
        want_model = False
    used_model = False

    # the guardrails look at the goal first, in every mode
    from nlq import refusal

    refused = bool(goal) and bool(refusal.check(goal))
    plan, recognised = P.match_plan(persona, goal, bool(case_id or golden_id))
    if plan not in allowed_plans(persona):
        plan, recognised = P.plans_for(persona)[0], False
    slots = dict(rule_slots)
    if refused:
        plan = P.get_plan(persona, "refused") or _guardrail_plan(persona)
        recognised = True
    elif want_model and goal:
        try:
            with llm_mode.use_mode(mode):
                out = _model("plan", {"persona": persona, "goal": goal,
                                      "plans": [{"id": p.id, "title": p.title, "description": p.description} for p in allowed_plans(persona)],
                                      "tools": sorted(allowed_tools(persona))})
            if out.get("_meta", {}).get("provider") == "offline":
                mode_note = "The language model was not reachable. Ran with rules instead."
            else:
                picked = validate_plan_output(out, persona, goal, request_text, session)
                if picked is None:
                    mode_note = "The language model's plan was not valid, so rules chose the plan."
                else:
                    plan = P.get_plan(persona, picked[0]) or plan
                    slots = {**slots, **picked[1]}
                    recognised = True
                    used_model = True
        except Exception as e:  # noqa: BLE001 - any model problem falls back to rules
            log.warning("assistant plan via model failed: %s", e)
            mode_note = "The language model could not be used. Ran with rules instead."

    if plan.id == "briefing":
        slots.pop("question", None)  # "give me my briefing" is not a question for a metric or policy tool

    if goal and not recognised:
        notes.append("The goal was not recognised, so this is your briefing. Try one of the suggested goals.")

    ctx = ToolContext(session=session, case_id=case_id, golden_id=golden_id, slots=slots, mode=mode)
    if not case_id and not golden_id and any(st.tool in CASE_TOOLS for st in plan.steps):
        ctx.facts["default_case"] = default_case_for(session)
    plan_out, steps, findings, proposals, problems = [], [], [], {}, []
    cites_all: list[dict] = []
    for n, st in enumerate(plan.steps, 1):
        sid = f"s{n}-{st.tool}"
        plan_out.append({"id": sid, "tool": st.tool, "title": st.title, "why": st.why})
        r = run_tool(st.tool, ctx, dict(st.args))
        step = {"id": sid, "tool": st.tool, "title": st.title, "status": r["status"], "ms": r["ms"], "summary": r["summary"],
                "evidence": r["evidence"]}
        if r["cites"]:
            step["cites"] = r["cites"]
            cites_all += r["cites"]
        steps.append(step)
        if r["status"] in ("done", "needs_approval"):
            findings += r["findings"]
            for p in r["proposals"]:
                proposals.setdefault(p["id"], p)
        else:
            problems.append(f"{st.title}: {r['summary']}")
    findings = notes + findings
    prop_list = list(proposals.values())

    # the summary
    persona_label = PERSONA_LABEL.get(persona, persona)
    summary = template_summary(persona_label, plan.title, findings, [p["title"] for p in prop_list], problems)
    if want_model and not refused and not (mode_note and not used_model):
        try:
            with llm_mode.use_mode(mode):
                out = _model("summary", {"persona": persona, "persona_label": persona_label, "goal": goal, "plan_title": plan.title,
                                         "steps": [{"tool": s["tool"], "status": s["status"], "summary": s["summary"]} for s in steps],
                                         "findings": findings, "proposals": [p["title"] for p in prop_list], "problems": problems})
            if out.get("_meta", {}).get("provider") != "offline":
                ok = validate_summary(out.get("summary"), _numbers(goal, steps, findings, prop_list))
                if ok:
                    summary, used_model = ok, True
                else:
                    mode_note = mode_note or "The language model's summary was not grounded in the evidence, so the standard summary is shown."
        except Exception as e:  # noqa: BLE001
            log.warning("assistant summary via model failed: %s", e)
            mode_note = mode_note or "The language model could not word the summary, so the standard summary is shown."

    audit_id = None
    try:
        audit_id = audit.record(
            session.user_id, persona, "assistant_run", "case" if (ctx.case_id) else "persona", ctx.case_id or persona,
            {"goal": goal, "case_id": case_id, "golden_id": golden_id, "mode": mode or "default"},
            {"plan": plan.id, "mode_used": "language model" if used_model else "rules",
             "steps": [{"id": s["id"], "tool": s["tool"], "status": s["status"], "ms": s["ms"], "summary": s["summary"]} for s in steps],
             "proposals": [p["id"] for p in prop_list], "never_executed": True})
    except Exception as e:  # noqa: BLE001 - the audit store must not take the screen down, but say so
        log.error("assistant run could not be audited: %s", e)
        findings.append("This run could not be written to the audit log.")

    log.info("assistant %s plan=%s %d steps in %.0f ms", persona, plan.id, len(steps), (time.perf_counter() - t0) * 1e3)
    return {"persona": persona, "goal": goal or "briefing", "plan_id": plan.id, "mode_used": "language model" if used_model else "rules",
            "mode_note": mode_note, "plan": plan_out, "steps": steps, "findings": findings, "proposals": prop_list,
            "summary": summary, "audit_id": audit_id,
            "case_id": ctx.case_id, "golden_id": ctx.golden_id}


def _guardrail_plan(persona: str) -> P.Plan:
    return P.Plan("refused", "Guardrail check", "A request that must be refused.",
                  (P.Step("guardrail_check", "Check the request against the guardrails", "Protected attributes and proxies are refused, always."),))
