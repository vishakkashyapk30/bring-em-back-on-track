from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from decisioning.schemas import Action


class DecisionIn(BaseModel):
    decision: Literal["approve", "edit", "override"]
    action: Action | None = None
    reason_code: Literal["customer_request", "hardship_suspected", "wrong_data", "other"] | None = None
    note: str | None = None


class WhatIfIn(BaseModel):
    case_id: str
    ptp_amount: float
    ptp_due_date: str
    split: list[dict] | None = None


class HardshipFlagIn(BaseModel):
    target: Literal["none", "possible", "clear"]
    reason: str | None = None
    program_id: str | None = None


class SimulatorIn(BaseModel):
    term_extension_months: int = 0
    payment_reduction_pct: float = 0.0
    rate_override: float | None = None
    payment_holiday_months: int = 0
    fee_waiver: bool = False
    program_id: str | None = None


class AskIn(BaseModel):
    question: str
    chips: dict | None = None


class PolicyQuestionIn(BaseModel):
    question: str
    case_id: str | None = None


class StressTestIn(BaseModel):
    channel: str | None = None
    agents_pct: float | None = None


class IdentityVerdictIn(BaseModel):
    verdict: Literal["link", "no_link", "unsure"]
