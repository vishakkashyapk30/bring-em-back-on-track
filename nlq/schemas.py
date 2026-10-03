from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Filter(BaseModel):
    field: str
    op: Literal["=", "!=", ">", ">=", "<", "<=", "in", "between", "like"] = "="
    value: Any = None


class TimeRange(BaseModel):
    start: str | None = None
    end: str | None = None
    label: str | None = None


class QueryTokens(BaseModel):
    intent: Literal["metric", "drivers", "comparison", "list", "rag_corpus", "rag_customer", "guardrail"]
    metric_id: str | None = None
    dimensions: list[str] = Field(default_factory=list)
    filters: list[Filter] = Field(default_factory=list)
    time_range: TimeRange | None = None
    sort: dict[str, str] | None = None
    limit: int | None = 1000
    out_of_scope: str | None = None


class Preflight(BaseModel):
    coverage_pct: float | None = None
    incidents: list[dict[str, Any]] = Field(default_factory=list)
    default_filters: list[str] = Field(default_factory=list)


class AskResponse(BaseModel):
    question: str
    chips: QueryTokens | None = None
    sql: str | None = None
    sql_source: Literal["semantic", "llm"] | None = None
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    insight: str | None = None
    caveats: list[str] = Field(default_factory=list)
    preflight: Preflight | None = None
    sources: list[str] = Field(default_factory=list)
    freshness: str | None = None  # when the data behind the answer was built (ISO, UTC); metric answers only
    followups: list[str] = Field(default_factory=list)
    answered_by: Literal["rules", "language model"] = "rules"
    mode_note: str | None = None  # why a requested language model was not used (e.g. not configured)
    refused: bool = False
    refusal_reason: str | None = None
