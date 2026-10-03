from __future__ import annotations

from pydantic import BaseModel, Field

from common.types import Channel, TimeBand, Treatment


class ReasonCode(BaseModel):
    code: str                 # e.g. CAP_7D_REACHED
    text: str                 # e.g. "No call: 3 of 3 contacts used this week"
    kind: str = "rule"        # rule | model | change | freshness


class Action(BaseModel):
    treatment: Treatment
    channel: Channel | None = None
    window: TimeBand | None = None
    program_id: str | None = None


class GateResult(BaseModel):
    allowed: list[Action]
    blocked: list[ReasonCode] = Field(default_factory=list)
    route_to_person: bool = False
    pressure_allowed: bool = True


class Explanation(BaseModel):
    recommendation: str
    rules_applied: list[ReasonCode]
    model_evidence: dict          # {p_break, band, label: "model estimate", drivers: [ReasonCode]}
    what_changed: list[ReasonCode]
    freshness: ReasonCode
    alternatives: list[dict]


class NbaProposal(BaseModel):
    case_id: str
    golden_id: str
    action: Action
    priority: float
    explanation: Explanation
