"""Request and response shapes for the persona assistant and the guided demo (the frontend is written against these)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class AssistantRunIn(BaseModel):
    goal: str | None = Field(default=None, max_length=500)
    case_id: str | None = None
    golden_id: str | None = None
    mode: Literal["rules", "llm"] | None = None  # the user's choice between deterministic rules and a language model


class Evidence(BaseModel):
    columns: list[str] | None = None
    rows: list[list[Any]] | None = None
    kv: list[list[str]] | None = None
    text: str | None = None
    links: list[dict[str, str]] | None = None


class Cite(BaseModel):
    doc_id: str
    section: str


class PlanStep(BaseModel):
    id: str
    tool: str
    title: str
    why: str


class Step(BaseModel):
    id: str
    tool: str
    title: str
    status: Literal["done", "skipped", "failed", "needs_approval"]
    ms: int
    summary: str
    evidence: Evidence = Field(default_factory=Evidence)
    cites: list[Cite] | None = None


class Proposal(BaseModel):
    id: str
    title: str
    detail: str
    kind: str
    href: str
    requires_role: str


class AssistantRun(BaseModel):
    persona: str
    goal: str
    mode_used: Literal["rules", "language model"]
    mode_note: str | None = None
    plan: list[PlanStep]
    steps: list[Step]
    findings: list[str]
    proposals: list[Proposal]
    summary: str
    audit_id: int | None = None
    plan_id: str | None = None
    case_id: str | None = None
    golden_id: str | None = None


class Goal(BaseModel):
    label: str
    goal: str


class Suggestions(BaseModel):
    persona: str
    briefing: Goal
    goals: list[Goal]


class JourneyCustomer(BaseModel):
    golden_id: str
    case_id: str
    name: str


class JourneyStage(BaseModel):
    id: str
    title: str
    narrative: str
    screen: str
    tool: str | None = None
    tool_args: dict[str, Any] | None = None
    why_it_matters: str
    evidence: Evidence = Field(default_factory=Evidence)
    human_step: str | None = None
    status: str | None = None
    summary: str | None = None
    ms: int | None = None


class Journey(BaseModel):
    persona: str
    title: str
    intro: str
    customer: JourneyCustomer | None = None
    stages: list[JourneyStage]
