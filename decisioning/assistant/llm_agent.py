# ruff: noqa: E501
"""The agentic assistant: a language model decides which tools to call, in what order, reads each result and writes a
grounded answer. A bounded JSON-action loop that works with any provider (no native function calling needed).

Each turn the model sees the persona, the goal, the context ids, the catalogue of tools THIS ROLE may use (never other
tools) and a compact digest of every step so far, and returns one JSON action:
    {"thought", "action": "call_tool" | "final", "tool", "args", "answer", "cited_steps", "emphasise"}

Safety is in code, not in the prompt:
- Every call goes through the same authorisation as the rule planner: the role's tools (decisioning.assistant.tools), row
  level access (api.access) for any case or customer id, and the Ask scope inside the nlq and rag tools. A denied call is a
  failed step; the model is told "not allowed" and never receives the data.
- Arguments are checked against the tool's schema; ids must appear in the goal, the request or an earlier result.
- At most 6 tool calls, 8 model turns and a 45 s wall-clock budget; an identical call is never repeated.
- The final answer must cite steps that exist, and every number and id in it must appear in the cited steps' evidence,
  else the template summary built from the steps is shown. Findings and proposals always come from the deterministic tool
  builders; the model may only say which proposals to put first. Nothing is ever written or sent.
- Any model error, invalid output after one repair, budget exhaustion or an unreachable provider raises AgentFallback and
  the caller runs the rule planner instead.
"""

from __future__ import annotations

import concurrent.futures as cf
import contextvars
import json
import logging
import os
import re
import time
from typing import Any

import jsonschema
from fastapi import HTTPException

from api.schemas.common import Session
from common.config import get_settings
from decisioning.assistant import plans as P
from decisioning.assistant.tools import TOOLS, ToolContext, default_case_for, run_tool
from llm.providers.offline import register

log = logging.getLogger(__name__)

MAX_CALLS = 6
MAX_TURNS = 8
BUDGET_S = 45.0
DIGEST_CHARS = 1500
FINISH_RESERVE_S = 12.0  # with less than this left, the next turn must be the final answer
PROMPT_ID = "assistant_agent"
EVIDENCE_STATUSES = ("done", "needs_approval")
NO_EVIDENCE = "I could not find evidence for that."

_POOL = cf.ThreadPoolExecutor(max_workers=4, thread_name_prefix="assistant-agent")


class AgentFallback(Exception):
    """The agent could not finish; the message says why (shown to the person in mode_note)."""


# ---------------------------------------------------------------- argument schemas the model sees

_Q = {"type": "string", "minLength": 3, "maxLength": 300, "description": "the question in plain words"}
_CASE = {"type": "string", "pattern": r"^CS-\d{4}-\d+$", "description": "a case id from the goal or an earlier result"}
_GOLD = {"type": "string", "pattern": r"^G-[A-Z0-9]{4,}$", "description": "a customer (golden) id from the goal or an earlier result"}
_DATE = {"type": "string", "pattern": r"^20\d{2}-\d{2}-\d{2}$", "description": "YYYY-MM-DD, from the goal or an earlier result"}
_CASE_ARGS = {"case_id": _CASE}
_CUSTOMER_ARGS = {"case_id": _CASE, "golden_id": _GOLD}

ARGS: dict[str, dict[str, dict]] = {
    "queue_summary": {"view": {"type": "string", "enum": ["all", "calls", "digital", "hardship", "vulnerable", "high_risk"]}},
    "customer_360": _CUSTOMER_ARGS,
    "identity_lineage": _CUSTOMER_ARGS,
    "nba_proposal": _CASE_ARGS,
    "eligibility_check": _CASE_ARGS,
    "call_summary": _CASE_ARGS,
    "promise_check": {**_CASE_ARGS, "date_override": _DATE},
    "simulator": {**_CASE_ARGS, "program_id": {"type": "string", "maxLength": 40, "description": "a program id from an eligibility result"},
                  "payment_cut_pct": {"type": "number", "minimum": 1, "maximum": 100, "description": "payment reduction in percent"},
                  "term_extension_months": {"type": "integer", "minimum": 1, "maximum": 60}},
    "policy_answer": {"question": _Q},
    "metric_question": {"question": _Q},
    "guardrail_check": {"question": _Q},
    "ask_data": {"question": _Q},
    "search_interactions": {"question": {**_Q, "description": "search words"}, **_CUSTOMER_ARGS},
    "stress_test": {"channel": {"type": "string", "enum": ["call", "sms", "email", "push"]},
                    "agents_pct": {"type": "number", "minimum": 0, "maximum": 0.9, "description": "share of agents absent, 0 to 0.9"}},
    "playbook_proposals": {"status": {"type": "string", "enum": ["pending_approval", "approved", "rejected"]}},
    "geo_map": {"metric": {"type": "string", "enum": ["broken_ptp_rate", "hardship_rate"]}},
    "audit_log": {"limit": {"type": "integer", "minimum": 1, "maximum": 30}},
}
REQUIRED: dict[str, list[str]] = {"ask_data": ["question"], "search_interactions": ["question"], "guardrail_check": ["question"]}
ID_ARGS = ("case_id", "golden_id", "program_id", "date_override")
CONTEXT_ID_TOOLS = {"customer_360", "identity_lineage", "nba_proposal", "eligibility_check", "call_summary", "promise_check", "simulator"}
CASE_TOOLS = CONTEXT_ID_TOOLS - {"identity_lineage"}

# where each tool reads from, for the Sources block (a label, not a query)
DATA_SOURCES = {
    "queue_summary": "features/nba_queue.parquet (nightly NBA queue)",
    "customer_360": "gold.c360_customer, gold.c360_account",
    "identity_lineage": "identity.identity_xref",
    "nba_proposal": "features/nba_queue.parquet and the policy gate (decisioning/config.yaml)",
    "eligibility_check": "silver.hardship_programs (eligibility rules)",
    "promise_check": "features/ptp_scores.parquet (promise-break model)",
    "call_summary": "silver.call_transcripts (redacted)",
    "hardship_board": "silver.contact_history, gold.c360_case",
    "missed_offers": "silver.offers, silver.hardship_programs",
    "override_report": "silver.offers, silver.agents",
    "simulator": "gold.c360_account, silver.hardship_programs",
    "batch_queue": "ops nba batches and features/nba_queue.parquet",
    "stress_test": "features/nba_queue.parquet (allocator re-run)",
    "guardrails": "ops nba_decisions and features/nba_queue.parquet",
    "team_agents": "silver.agents",
    "scorecard": "strategy scorecard (gold layer)",
    "geo_map": "gold.c360_customer by postal area (FSA)",
    "model_card": "reports/model_eval.json",
    "fairness_report": "reports/fairness.json",
    "identity_queue": "identity review queue",
    "data_quality": "reports/data_quality.json",
    "contract_tests": "reports/data_quality.json (contract tests)",
    "feature_parity": "reports/feature_parity.json",
    "monitoring": "monitoring summary (freshness, contract tests, parity)",
    "audit_log": "ops audit_log (append-only)",
    "employer_radar": "silver.deposit_accounts, silver.customers by employer (employers under 10 customers hidden)",
    "playbook_proposals": "ops playbook_proposals (nothing is sent until a team lead approves)",
    "outage_victims": "silver.card_statements, silver.loan_instalments, silver.promises_to_pay in the outage window (silver.ops_events)",
    "data_drift": "silver.ops_events and a week-on-week profile of silver.contact_history; ops drift_fixes (drafts only)",
    "call_friction": "silver.call_transcripts, silver.voice_samples (call-level measures only)",
}

ACTION_CLAIM = re.compile(r"\b(i|we|the assistant)\s+(have\s+|has\s+|just\s+)?(sent|approved|emailed|texted|called|contacted|changed|"
                          r"updated|saved|offered|scheduled|lowered|cleared|executed|released|wrote|written|deleted)\b", re.I)
ID_RE = re.compile(r"\b[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+\b")
NUM_RE = re.compile(r"\d+(?:[.,]\d+)*")
STEP_REF = re.compile(r"\[?\b(s\d+)(?:-[a-z_]+)?\b\]?")
SQL_RE = re.compile(r"SQL used:\s*\n(.+)", re.S)
TABLE_RE = re.compile(r"\b(?:FROM|JOIN)\s+([A-Za-z_][\w.]*)", re.I)


# ---------------------------------------------------------------- the model, behind one function (tests replace it)

def _model(inputs: dict) -> dict:
    from llm.client import complete_json

    return complete_json(PROMPT_ID, 1, inputs, PROMPT_ID)


def _forget_cached(inputs: dict) -> None:
    """complete_json caches an offline fallback under the configured provider's key; drop it so a rate-limited turn is
    asked again next time instead of falling back forever. Mirrors the key in llm/client.py."""
    try:
        from common.hashing import stable_hash
        from common.llm_mode import effective_provider

        s = get_settings()
        name = effective_provider()
        key = stable_hash([name, getattr(s, f"{name}_model", None), PROMPT_ID, 1, inputs])
        (s.llm_cache_dir / f"{key}.json").unlink(missing_ok=True)
    except Exception:  # noqa: BLE001 - best effort
        pass


def _call_model(inputs: dict, timeout: float) -> dict:
    """One model turn in a worker thread so the wall-clock budget holds even when a provider is slow."""
    ctx = contextvars.copy_context()  # carries the request's mode (rules / llm) and Ask scope
    fut = _POOL.submit(ctx.run, lambda: _model(inputs))
    return fut.result(timeout=max(timeout, 0.5))


# ---------------------------------------------------------------- the catalogue (only what the role may use)

def allowed_tools(persona: str) -> list[str]:
    return sorted(n for n, t in TOOLS.items() if persona in t.roles)


def arg_schema(tool: str) -> dict:
    return {"type": "object", "properties": ARGS.get(tool, {}), "required": REQUIRED.get(tool, []), "additionalProperties": False}


def catalogue(persona: str) -> list[dict]:
    out = []
    for n in allowed_tools(persona):
        props = ARGS.get(n, {})
        out.append({"name": n, "description": TOOLS[n].description,
                    "args": {k: {kk: vv for kk, vv in v.items() if kk in ("type", "enum", "description", "minimum", "maximum")}
                             for k, v in props.items()},
                    "required": REQUIRED.get(n, [])})
    return out


def _titles() -> dict[str, str]:
    t: dict[str, str] = {}
    for plans in P.PLANS.values():
        for p in plans:
            for st in p.steps:
                t.setdefault(st.tool, st.title)
    return t


TITLES = _titles()


def title_for(tool: str) -> str:
    if tool in TITLES:
        return TITLES[tool]
    if tool in TOOLS:
        return TOOLS[tool].description.split(":")[0].split(".")[0][:60]
    return "Rejected call"


# ---------------------------------------------------------------- what the model sees of a step (no names, capped)

def _names(ev: dict) -> list[str]:
    names: list[str] = []
    cols = ev.get("columns") or []
    for i, c in enumerate(cols):
        if c in ("Customer", "Name", "Source record", "Candidate"):
            names += [str(r[i]) for r in ev.get("rows") or [] if i < len(r) and r[i]]
    for k, v in ev.get("kv") or []:
        if k == "Customer" and v:
            names.append(str(v).split(" (")[0])
    return names


def digest(r: dict) -> str:
    """A compact view of one step for the model: summary, key facts, the first rows, findings and proposal ids. Customer
    and agent names are masked and direct PII patterns redacted before anything leaves the machine."""
    from llm.redact import redact

    if r["status"] not in EVIDENCE_STATUSES:
        return f"{r['status']}: {r['summary']}"
    ev = r.get("evidence") or {}
    parts = [f"summary: {r['summary']}"]
    if ev.get("kv"):
        parts.append("facts: " + "; ".join(f"{k}={v}" for k, v in ev["kv"][:14]))
    if ev.get("columns") and ev.get("rows"):
        parts.append("table: " + " | ".join(map(str, ev["columns"])))
        parts += ["  " + " | ".join("" if x is None else str(x) for x in row) for row in ev["rows"][:6]]
    if ev.get("text"):
        parts.append("text: " + str(ev["text"])[:400])
    if r.get("findings"):
        parts.append("findings: " + " ".join(r["findings"][:4]))
    if r.get("proposals"):
        parts.append("proposals (a person approves): " + "; ".join(f"{p['id']}: {p['title']}" for p in r["proposals"][:4]))
    text = redact("\n".join(parts), _names(ev))
    return text[:DIGEST_CHARS]


# ---------------------------------------------------------------- grounding of the final answer

def _canon(n: str) -> str:
    n = n.replace(",", "").rstrip(".")
    if "." in n:
        a, b = n.split(".", 1)
        b = b.rstrip("0")
        a = a.lstrip("0") or "0"
        return f"{a}.{b}" if b else a
    return n.lstrip("0") or "0"


def evidence_text(*chunks: Any) -> str:
    return " ".join(json.dumps(c, default=str) if not isinstance(c, str) else c for c in chunks)


def _numbers(text: str) -> tuple[set[str], list[float]]:
    toks = NUM_RE.findall(text)
    canon = {_canon(t) for t in toks}
    floats = []
    for t in canon:
        try:
            floats.append(float(t))
        except ValueError:
            pass
    return canon, floats


def number_ok(tok: str, canon: set[str], floats: list[float]) -> bool:
    """Formatting-tolerant: 1,326 = 1326; 0.30 = 0.3; 30% = 0.30; 0.2987 may be written 0.30; 1325.6 may be written 1,326."""
    c = _canon(tok)
    if c in canon:
        return True
    try:
        v = float(c)
    except ValueError:
        return False
    d = len(c.split(".")[1]) if "." in c else 0
    half = 0.5 * 10 ** -d + 1e-9  # rounding half up at the precision the answer was written in
    for e in floats:
        if e < 1.0001 and abs(e * 100 - v) <= half:  # a share written as a percent
            return True
        if d >= 1 and abs(e - v) <= half:
            return True
        if d == 0 and v >= 10 and e != int(e) and abs(e - v) <= 0.5:
            return True
    return False


def check_answer(answer: Any, cited: Any, steps: list[dict], results: dict[str, dict], goal: str,
                 context_ids: list[str]) -> tuple[str | None, list[str], str]:
    """(clean answer or None, the cited step ids that hold evidence, why it was rejected)."""
    from common.protected import PROTECTED_ATTRIBUTES

    if not isinstance(answer, str) or not answer.strip():
        return None, [], "the answer was empty"
    text = " ".join(answer.split())
    if len(text) > 1500:
        return None, [], "the answer was too long"
    ids = {s["id"] for s in steps}
    short = {s["id"].split("-")[0]: s["id"] for s in steps}
    cited_ids: list[str] = []
    for c in cited if isinstance(cited, list) else []:
        c = str(c).strip().strip("[]")
        base = c.split("-")[0]
        full = c if c in ids else short.get(base) if re.fullmatch(r"s\d+", base) else None
        if full is None:
            return None, [], f"it cited a step that does not exist ({c[:20]})"
        if full not in cited_ids:
            cited_ids.append(full)
    for m in STEP_REF.finditer(text):  # inline [s2] markers must be real steps too
        if m.group(1) not in short:
            return None, [], f"it referred to a step that does not exist ({m.group(1)})"
        if short[m.group(1)] not in cited_ids:
            cited_ids.append(short[m.group(1)])
    with_ev = [c for c in cited_ids if results.get(c, {}).get("status") in EVIDENCE_STATUSES]
    if not with_ev:
        return None, [], "it did not cite a step with evidence"
    if ACTION_CLAIM.search(text):
        return None, [], "it claimed an action was taken (the assistant only proposes)"
    low = text.lower()
    if any(re.search(rf"\b{re.escape(n)}\b", low) for n in PROTECTED_ATTRIBUTES):
        return None, [], "it mentioned a protected attribute"
    ev = evidence_text(goal, " ".join(context_ids), *[_step_evidence(results[c]) for c in with_ev])
    ev_low = ev.lower()
    body = STEP_REF.sub(" ", text)
    for m in ID_RE.finditer(body):
        if any(ch.isdigit() for ch in m.group(0)) and m.group(0).lower() not in ev_low:
            return None, [], f"the id {m.group(0)} is not in the cited evidence"
    body = ID_RE.sub(" ", body)
    canon, floats = _numbers(ev)
    for tok in NUM_RE.findall(body):
        if not number_ok(tok, canon, floats):
            return None, [], f"the number {tok} is not in the cited evidence"
    claim = unsupported_sentence(STEP_REF.sub(" ", text), evidence_text(*[_step_evidence(results[c]) for c in with_ev]))
    if claim:
        return None, [], f"a sentence is not supported by the cited evidence ({claim})"
    return text, with_ev, ""


STOP = frozenset("""about above after again also among because been before being below between both but could does doing
    down during each either even every from further have having here into just like more most much must need needs only other
    over same should some such than that their them then there these they this those through under until very want were what
    when where which while will with within without would your yours today first next please case cases customer customers
    approve approval approves person people wait waits waiting model estimate cause effect evidence found shows shown says
    said tell check review step steps answer based according result results""".split())
WORD_RE = re.compile(r"[a-z][a-z']{3,}")


def unsupported_sentence(text: str, evidence: str, share: float = 0.4) -> str | None:
    """Lexical support: in every sentence with three or more content words, at least `share` of them (matched on their
    first five letters) must appear in the cited evidence. Catches claims with no numbers that the evidence never made."""
    have = {w[:5] for w in WORD_RE.findall(evidence.lower())}
    for sent in re.split(r"(?<=[.!?])\s+", text):
        words = [w for w in WORD_RE.findall(sent.lower()) if w not in STOP]
        if len(words) >= 3 and sum(w[:5] in have for w in words) / len(words) < share:
            return sent[:80]
    return None


def _step_evidence(r: dict) -> list:
    return [r.get("summary", ""), r.get("evidence", {}), r.get("findings", []),
            [{k: p.get(k) for k in ("id", "title", "detail")} for p in r.get("proposals", [])]]


# ---------------------------------------------------------------- citations (shared with the rules runner)

def _cite_kind(c: dict) -> str:
    if c.get("kind"):
        return str(c["kind"])
    if c.get("source") in ("note", "transcript", "voice") or "turn_index" in c:
        return "interaction"
    if "sql" in c or ("ref" in c and "tables" in c):
        return "sql"
    return "policy"


def collect_citations(steps: list[dict], cited: list[str] | None = None) -> list[dict]:
    """The Sources block. One `step` entry per cited step with evidence, then the underlying sources flattened from those
    steps: the raw citations the nlq and rag tools returned (passed through unchanged, plus `kind` and `step_id`), the
    documents a step cites, the SQL it ran (with its tables) and the data product it read."""
    out: list[dict] = []
    seen: set[str] = set()

    def add(d: dict) -> None:
        k = json.dumps(d, sort_keys=True, default=str)
        if k not in seen:
            seen.add(k)
            out.append(d)

    for s in steps:
        if (cited is not None and s["id"] not in cited) or s.get("status") not in EVIDENCE_STATUSES:
            continue
        sid, ev = s["id"], s.get("evidence") or {}
        add({"kind": "step", "step_id": sid, "tool": s["tool"], "label": f"{s.get('title', s['tool'])}: {s.get('summary', '')}"[:200]})
        raw = [c for c in ev.get("cites") or [] if isinstance(c, dict)]
        for c in raw:
            add({**c, "kind": _cite_kind(c), "step_id": sid})
        raw_docs = {(str(c.get("doc_id")), str(c.get("section"))) for c in raw}
        for c in s.get("cites") or []:
            if (str(c.get("doc_id")), str(c.get("section"))) not in raw_docs and not any(
                    str(c.get("doc_id")) == str(r.get("doc_id")) for r in raw):
                kind = "interaction" if str(c.get("section", "")).startswith("turn") else "document"
                add({"kind": kind, "doc_id": c.get("doc_id"), "section": c.get("section"), "step_id": sid})
        m = SQL_RE.search(str(ev.get("text") or ""))
        if m and not any(_cite_kind(c) == "sql" for c in raw):
            sql = m.group(1).strip()
            add({"kind": "sql", "ref": sql, "tables": sorted(set(TABLE_RE.findall(sql))), "step_id": sid})
        if s["tool"] in DATA_SOURCES:
            add({"kind": "data", "ref": DATA_SOURCES[s["tool"]], "step_id": sid})
    return out


# ---------------------------------------------------------------- model output

def parse_action(out: Any) -> tuple[dict | None, str]:
    from llm.client import load_schema

    if not isinstance(out, dict):
        return None, "the reply was not a JSON object"
    clean = {k: v for k, v in out.items() if k != "_meta"}
    try:
        jsonschema.validate(clean, load_schema(PROMPT_ID))
    except jsonschema.ValidationError as e:
        return None, f"the reply did not match the schema: {e.message[:160]}"
    act = clean["action"]
    if act == "call_tool":
        if not isinstance(clean.get("tool"), str) or not clean["tool"].strip():
            return None, "action call_tool needs a tool name"
        args = clean.get("args") or {}
        if not isinstance(args, dict):
            return None, "args must be an object"
        clean["args"] = {k: v for k, v in args.items() if v not in (None, "")}
    elif not isinstance(clean.get("answer"), str) or not clean["answer"].strip():
        return None, "action final needs an answer"
    return clean, ""


# ---------------------------------------------------------------- the loop

def _authorise_ids(session: Session, args: dict) -> str | None:
    from api import access

    for k, fn in (("case_id", access.case), ("golden_id", access.lineage)):
        if args.get(k):
            try:
                fn(session, args[k])
            except HTTPException as e:
                d = e.detail
                return (d.get("reason") if isinstance(d, dict) else str(d)) or "Not allowed."
    return None


def run(session: Session, goal: str, case_id: str | None = None, golden_id: str | None = None, mode: str | None = None,
        *, budget_s: float | None = None) -> dict:
    """Run the agent. Returns the assistant response (same contract as the rules runner, plus model_turns, trace,
    citations, emphasis, stop_reason). Raises AgentFallback when the rule planner must run instead."""
    from common.llm_mode import effective_provider
    from decisioning.assistant import runner
    from governance import audit

    t0 = time.perf_counter()
    persona = getattr(session.role, "value", str(session.role))
    budget = float(budget_s or os.environ.get("ASSISTANT_AGENT_BUDGET_S") or BUDGET_S)
    allowed = set(allowed_tools(persona))
    tools_seen = catalogue(persona)
    ctx = ToolContext(session=session, case_id=case_id, golden_id=golden_id, slots={}, mode=mode)
    context_ids = [x for x in (case_id, golden_id) if x]
    known = [goal, *context_ids]  # ids the model may use: the goal, the request, and every result so far
    steps: list[dict] = []
    results: dict[str, dict] = {}
    observations: list[dict] = []
    notes: list[str] = []
    trace: list[dict] = []
    seen_calls: dict[str, str] = {}
    turns = calls = 0
    repair: str | None = None
    final: dict | None = None
    configured = effective_provider()

    def fail_step(tool: str, args: dict, summary: str, thought: str) -> None:
        safe = re.sub(r"[^a-z0-9_]", "", tool.lower())[:40] or "unknown"
        sid = f"s{len(steps) + 1}-{safe}"
        r = {"status": "failed", "summary": summary, "evidence": {}, "cites": [], "findings": [], "proposals": [], "ms": 0}
        steps.append({"id": sid, "tool": safe, "title": title_for(safe), "status": "failed", "ms": 0, "summary": summary,
                      "evidence": {}, "why": thought})
        results[sid] = r
        observations.append({"step": sid, "tool": safe, "args": args, "status": "failed", "result": "not allowed: " + summary})

    while True:
        elapsed = time.perf_counter() - t0
        if turns >= MAX_TURNS:
            raise AgentFallback(f"The language model did not finish within {MAX_TURNS} turns.")
        if elapsed >= budget:
            raise AgentFallback(f"The language model used up the {budget:.0f}-second budget.")
        must_finish = calls >= MAX_CALLS or turns >= MAX_TURNS - 1 or (budget - elapsed) < FINISH_RESERVE_S
        inputs = {"persona": runner.PERSONA_LABEL.get(persona, persona), "role": persona, "goal": goal,
                  "context": {"case_id": case_id, "golden_id": golden_id,
                              "case_in_focus": ctx.case_id or ctx.facts.get("default_case"),
                              "customer_in_focus": ctx.golden_id or ctx.facts.get("default_golden"),
                              "today": str(get_settings().as_of_date)},
                  "tools": tools_seen, "observations": observations, "notes": notes[-4:],
                  "tool_calls_left": max(MAX_CALLS - calls, 0), "turns_left": MAX_TURNS - turns, "must_finish": must_finish}
        if repair:
            inputs["repair"] = f"Your last reply was not valid: {repair}. Reply with one JSON object that follows the rules."
        turns += 1
        try:
            out = _call_model(inputs, budget - elapsed)
        except cf.TimeoutError as e:
            raise AgentFallback(f"The language model used up the {budget:.0f}-second budget.") from e
        except Exception as e:  # noqa: BLE001 - bad JSON or a broken provider: one repair, then rules
            log.warning("assistant agent turn %d failed: %s", turns, e)
            if repair is not None:
                raise AgentFallback("The language model could not be used.") from e
            repair = f"{type(e).__name__}"
            continue
        meta = out.get("_meta", {}) if isinstance(out, dict) else {}
        if meta.get("provider") == "offline":  # the provider fell back (or none is configured): that is not a model
            if configured != "offline":
                _forget_cached(inputs)
            raise AgentFallback("The language model was not reachable.")
        act, err = parse_action(out)
        if act is None or (must_finish and act["action"] == "call_tool"):
            err = err or "no tool calls are left, so the action must be final"
            if repair is not None:
                raise AgentFallback(f"The language model's reply was not valid twice ({err}).")
            repair = err
            continue
        repair = None
        thought = str(act.get("thought") or "")[:240]
        trace.append({"turn": turns, "thought": thought, "action": act["action"], "tool": act.get("tool"),
                      "args": act.get("args") or {}})
        if act["action"] == "final":
            final = act
            break

        tool, args = act["tool"].strip(), dict(act.get("args") or {})
        key = json.dumps([tool, args], sort_keys=True, default=str)
        if key in seen_calls:
            notes.append(f"{tool} with these arguments already ran as {seen_calls[key]}; use that result, call something else or answer.")
            continue
        seen_calls[key] = f"s{len(steps) + 1}"
        calls += 1
        if tool not in TOOLS:
            fail_step(tool, args, f"Rejected: there is no tool called {tool[:40]}. No data was read.", thought)
            continue
        if tool not in allowed:
            fail_step(tool, args, f"Not allowed: the {persona.replace('_', ' ')} role may not use {tool}. No data was read.", thought)
            continue
        if args.get("payment_cut_pct") is not None and isinstance(args["payment_cut_pct"], (int, float)) and 0 < args["payment_cut_pct"] <= 1:
            args["payment_cut_pct"] = args["payment_cut_pct"] * 100  # 0.5 means 50%
        try:
            jsonschema.validate(args, arg_schema(tool))
        except jsonschema.ValidationError as e:
            fail_step(tool, args, f"Rejected: the arguments for {tool} were not valid ({e.message[:120]}). No data was read.", thought)
            continue
        known_low = evidence_text(*known).lower()
        bad = next((str(args[k]) for k in ID_ARGS if args.get(k) and str(args[k]).lower() not in known_low), None)
        if bad:
            fail_step(tool, args, f"Rejected: {bad} does not appear in the goal or in an earlier result, so it was not used. No data was read.", thought)
            continue
        denied = _authorise_ids(session, args)
        if denied:
            fail_step(tool, args, f"Not allowed: {denied} No data was read.", thought)
            continue

        kwargs = dict(args)
        if tool in CONTEXT_ID_TOOLS:  # ids set the case or customer in focus, exactly as the screens would
            cid, gid = kwargs.pop("case_id", None), kwargs.pop("golden_id", None)
            if cid:
                ctx.case_id, ctx.golden_id = cid, gid
                ctx.facts.pop("default_golden", None)
                ctx.facts["default_case"] = cid
            elif gid:
                ctx.golden_id, ctx.case_id = gid, None
                ctx.facts.pop("default_case", None)
                ctx.facts["default_golden"] = gid
            if (tool in CASE_TOOLS and not ctx.case_id and not ctx.golden_id and not ctx.facts.get("default_case")
                    and not ctx.facts.get("default_golden") and persona in ("agent", "hardship_specialist", "team_lead")):
                ctx.facts["default_case"] = default_case_for(session)
        sid = f"s{len(steps) + 1}-{tool}"
        r = run_tool(tool, ctx, kwargs)
        step = {"id": sid, "tool": tool, "title": title_for(tool), "status": r["status"], "ms": r["ms"], "summary": r["summary"],
                "evidence": r["evidence"], "why": thought}
        if r["cites"]:
            step["cites"] = r["cites"]
        steps.append(step)
        results[sid] = r
        observations.append({"step": sid, "tool": tool, "args": args, "status": r["status"], "result": digest(r)})
        if r["status"] in EVIDENCE_STATUSES:
            known.append(evidence_text(*_step_evidence(r)))

    # ---------------------------------------------------------------- the answer, checked
    findings: list[str] = []
    proposals: dict[str, dict] = {}
    problems: list[str] = []
    for s in steps:
        r = results[s["id"]]
        if r["status"] in EVIDENCE_STATUSES:
            findings += r["findings"]
            for p in r["proposals"]:
                proposals.setdefault(p["id"], p)
        else:
            problems.append(f"{s['title']}: {r['summary']}")
    emphasis = [str(x) for x in (final.get("emphasise") or []) if str(x) in proposals][:3]
    prop_list = [proposals[i] for i in emphasis] + [p for k, p in proposals.items() if k not in emphasis]
    persona_label = runner.PERSONA_LABEL.get(persona, persona)
    evidence_steps = [s["id"] for s in steps if s["status"] in EVIDENCE_STATUSES]
    mode_note = None
    stop_reason = "answered"
    if not evidence_steps:
        summary = NO_EVIDENCE + (" " + "; ".join(problems[:2]) if problems else "")
        cited, grounded, stop_reason = [], False, "no evidence"
    else:
        text, cited, why = check_answer(final.get("answer"), final.get("cited_steps") or [], steps, results, goal, context_ids)
        grounded = text is not None
        if grounded:
            summary = text
        else:
            summary = runner.template_summary(persona_label, "Assistant run", findings, [p["title"] for p in prop_list], problems)
            cited = evidence_steps
            mode_note = f"The language model's answer was not used because {why}, so the summary is built from the steps."
            stop_reason = "answer replaced"
    citations = collect_citations(steps, cited)

    plan_out = [{"id": s["id"], "tool": s["tool"], "title": s["title"], "why": s.pop("why") or "Chosen by the language model."} for s in steps]
    audit_id = None
    try:
        audit_id = audit.record(
            session.user_id, persona, "assistant_run", "case" if ctx.case_id else "persona", ctx.case_id or persona,
            {"goal": goal, "case_id": case_id, "golden_id": golden_id, "mode": mode or "default"},
            {"plan": "agent", "mode_used": "language model", "model_turns": turns, "tool_calls": calls, "stop_reason": stop_reason,
             "grounded": grounded, "steps": [{"id": s["id"], "tool": s["tool"], "status": s["status"], "ms": s["ms"],
                                               "summary": s["summary"]} for s in steps],
             "trace": trace, "cited_steps": cited, "proposals": [p["id"] for p in prop_list], "never_executed": True})
    except Exception as e:  # noqa: BLE001 - the audit store must not take the screen down, but say so
        log.error("assistant agent run could not be audited: %s", e)
        findings.append("This run could not be written to the audit log.")

    log.info("assistant agent %s: %d turns, %d calls in %.0f ms (%s)", persona, turns, calls, (time.perf_counter() - t0) * 1e3, stop_reason)
    return {"persona": persona, "goal": goal, "plan_id": "agent", "mode_used": "language model", "mode_note": mode_note,
            "plan": plan_out, "steps": steps, "findings": findings, "proposals": prop_list, "summary": summary,
            "audit_id": audit_id, "case_id": ctx.case_id, "golden_id": ctx.golden_id,
            "citations": citations, "model_turns": turns, "tool_calls": calls, "stop_reason": stop_reason,
            "grounded": grounded, "emphasis": emphasis, "trace": trace,
            "elapsed_ms": round((time.perf_counter() - t0) * 1000)}


# ---------------------------------------------------------------- offline handler (LLM_PROVIDER=offline always works)

@register(PROMPT_ID)
def _offline(inputs: dict) -> dict:
    """The rule plan, one step per turn, then an answer made of the steps' own summaries. Deterministic. The runner
    treats an offline reply as "no model" and runs the rules directly; tests use this to drive the loop."""
    persona, goal = inputs.get("role", ""), inputs.get("goal", "")
    obs = inputs.get("observations", [])
    names = {t["name"] for t in inputs.get("tools", [])}
    plan, _ = P.match_plan(persona, goal, bool((inputs.get("context") or {}).get("case_id")))
    steps = [s for s in plan.steps if s.tool in names]
    if not inputs.get("must_finish") and len(obs) < len(steps):
        st = steps[len(obs)]
        args = {k: v for k, v in st.args.items() if k in ARGS.get(st.tool, {})}
        return {"thought": st.why, "action": "call_tool", "tool": st.tool, "args": args, "answer": None, "cited_steps": []}
    good = [o for o in obs if o.get("status") in EVIDENCE_STATUSES]
    answer = " ".join(f"{o['result'].split(chr(10))[0].removeprefix('summary: ')} [{o['step'].split('-')[0]}]" for o in good[:4])
    return {"thought": "Enough evidence to answer.", "action": "final", "tool": None, "args": {},
            "answer": answer or NO_EVIDENCE, "cited_steps": [o["step"] for o in good]}
