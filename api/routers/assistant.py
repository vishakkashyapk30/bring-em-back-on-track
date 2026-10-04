from typing import Any

from fastapi import APIRouter, Depends

from api.deps import require
from api.schemas.assistant import AssistantRun, AssistantRunIn, Evidence, Step, Suggestions
from common.types import Role
from decisioning.assistant import plans, runner

router = APIRouter(prefix="/assistant", tags=["assistant"])
EVERYONE = {Role.agent, Role.hardship_specialist, Role.team_lead, Role.analyst, Role.steward}


class RunEvidence(Evidence):
    cites: list[dict[str, Any]] | None = None  # raw citations from nlq and rag, passed through unchanged


class RunStep(Step):
    evidence: RunEvidence = RunEvidence()


class AssistantRunOut(AssistantRun):
    """The run, plus the agent's extras. `citations` is the Sources block: {kind: step, step_id, tool, label} for each
    cited step, then the sources under them: policy {doc_id, section, quote}, interaction {source, doc_id, turn_index,
    quote, ...}, sql {ref, tables}, document {doc_id, section} and data {ref}, each with its step_id."""

    steps: list[RunStep]
    citations: list[dict[str, Any]] = []
    model_turns: int = 0
    tool_calls: int | None = None
    stop_reason: str | None = None
    grounded: bool | None = None
    emphasis: list[str] = []
    trace: list[dict[str, Any]] = []
    elapsed_ms: int | None = None


@router.get("/suggestions")
def suggestions(s=Depends(require(EVERYONE))) -> Suggestions:
    """The goals that work for the signed-in persona; each one is checked by tests/unit/test_assistant.py."""
    role = s.role.value if hasattr(s.role, "value") else str(s.role)
    ps = plans.plans_for(role)
    return Suggestions.model_validate({
        "persona": role,
        "briefing": {"label": ps[0].label, "goal": ps[0].goal},
        "goals": [{"label": p.label, "goal": p.goal} for p in ps[1:] if p.label]})


@router.post("/run")
def run(body: AssistantRunIn, s=Depends(require(EVERYONE))) -> AssistantRunOut:
    """Plan (rules) or let a language model choose the tools (agent), call real tools, show every step with its
    evidence and sources, and propose actions a person approves in the existing screens. Read-only: the assistant never
    changes customer data or contacts anyone. Every run is audited."""
    return AssistantRunOut.model_validate(runner.run(s, body.goal, body.case_id, body.golden_id, body.mode))
