from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from common.types import Channel, TimeBand, Treatment


class ReasonCode(BaseModel):
    code: str                 # e.g. CAP_7D_REACHED
    text: str                 # e.g. "No call: 3 of 3 contacts used this week"
    kind: str = "rule"        # rule | model | change | freshness
    contribution: float | None = None


class Action(BaseModel):
    treatment: Treatment
    channel: Channel | None = None
    window: TimeBand | None = None
    program_id: str | None = None
    # The instant the action is planned for (customer-local rules are judged at this time). Not sent to the UI.
    scheduled_at: datetime | None = Field(default=None, exclude=True)


class BlockedAction(BaseModel):
    treatment: Treatment
    channel: Channel | None = None
    code: str


class GateResult(BaseModel):
    """What the plain contact rules allow, before any model runs."""

    disposition: str          # contact_allowed | no_contact | route_to_person | paused
    allowed: list[Action] = Field(default_factory=list)
    blocked: list[BlockedAction] = Field(default_factory=list)
    rules_fired: list[ReasonCode] = Field(default_factory=list)
    route_to: str | None = None
    pressure_removed: bool = False

    def permits(self, treatment: str, channel: str | None) -> bool:
        return any(a.treatment == treatment and a.channel == channel for a in self.allowed)

    def reason_for(self, treatment: str, channel: str | None) -> str | None:
        code = next((b.code for b in self.blocked if b.treatment == treatment and b.channel == channel), None)
        return next((r.text for r in self.rules_fired if r.code == code), None) if code else None


class Explanation(BaseModel):
    recommendation: str
    rules_applied: list[ReasonCode]
    model_evidence: dict          # {p_break, band, label: "model estimate", drivers: [ReasonCode]}
    what_changed: list[ReasonCode]
    freshness: ReasonCode
    alternatives: list[dict]
    generated_by: str = "template"


class NbaProposal(BaseModel):
    case_id: str
    golden_id: str
    action: Action
    priority: float
    explanation: Explanation
    route_to: str | None = None
    review_mode: str = "individual"
