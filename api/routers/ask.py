from fastapi import APIRouter, Depends

from api.deps import live_data, require, stub
from api.schemas.nba import AskIn
from common.types import Role
from governance import audit
from nlq.schemas import AskResponse, Preflight

router = APIRouter(tags=["ask"])

FOLLOWUPS = {
    "metric": ["Split it by province", "Compare with the previous month", "Only randomised cases"],
    "policy": ["Which policy section covers this?", "What does the FAQ say?"],
}


@router.post("/ask")
def ask(body: AskIn, s=Depends(require({Role.analyst, Role.team_lead, Role.agent}))) -> AskResponse:
    """Collections Ask (Layer 2): refusals, cited policy answers, call summaries, certified-metric SQL."""
    if not live_data():
        from nlq import refusal

        reason = refusal.check(body.question, None)
        if reason:
            audit.record(s.user_id, s.role, "refusal", "question", None, {"q": body.question}, reason)
            return AskResponse(question=body.question, refused=True, refusal_reason=reason)
        return AskResponse.model_validate({**stub("ask"), "question": body.question})
    from nlq.pipeline import ask as run

    a = run(body.question, None)
    if a.kind == "metric" and s.role == Role.agent:
        # Agents work their own customers in the C360; portfolio-wide metrics are for analysts and team leads.
        reason = "Refused: portfolio metrics are available to analysts and team leads. Agents see their own customers in the C360."
        audit.record(s.user_id, s.role, "refusal", "question", None, {"q": body.question}, reason)
        return AskResponse(question=body.question, refused=True, refusal_reason=reason)
    audit.record(s.user_id, s.role, "refusal" if a.refused else "query", "question", None,
                 {"q": body.question}, {"kind": a.kind, "sql_or_sources": a.sql_or_sources})
    if a.refused:
        return AskResponse(question=body.question, refused=True, refusal_reason=a.refusal_reason)
    chips = None
    if a.kind == "metric":
        c = a.chips
        chips = {"intent": "metric", "metric_id": c.get("metric"), "dimensions": c.get("dimensions", []),
                 "filters": [{"field": "filter", "op": "=", "value": f} for f in c.get("filters", [])],
                 "time_range": {"label": c["time"]} if c.get("time") else None, "sort": None, "limit": None,
                 "out_of_scope": None}
    insight = None
    if a.kind == "metric" and a.rows:
        insight = f"{len(a.rows)} row(s) returned from the certified {a.chips.get('metric')} definition."
    elif a.kind in ("policy", "call_summary"):
        insight = a.answer
    incidents = [{"event_id": c.split(": ")[1] if c.count(": ") >= 2 else "incident", "text": c.split(": ", 2)[-1]}
                 for c in a.caveats if c.startswith("Incident")]
    return AskResponse(
        question=body.question, chips=chips, sql=a.sql_or_sources if a.kind == "metric" else None,
        sql_source="semantic" if a.kind == "metric" else None, columns=a.columns,
        rows=[[v if isinstance(v, (int, float, str, bool)) or v is None else str(v) for v in r] for r in a.rows],
        insight=insight, caveats=[c for c in a.caveats if not c.startswith("Incident")],
        preflight=Preflight(incidents=incidents) if incidents else None,
        sources=[a.sql_or_sources] if a.kind != "metric" else ["silver (typed release tables)"],
        freshness=a.freshness,
        followups=FOLLOWUPS.get(a.kind, []), refused=False)
