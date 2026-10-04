"""Track: one subject per persona, followed over time. Response contract for /api/track (api/routers/track.py).

Every insight carries a plain-English reason and its source (the SQL that produced it, or the record ids behind it).
Analyst views hold aggregates only: no row in an analyst response names a customer, case or account.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Kind = Literal["customer", "agent", "employer", "cohort", "identity", "product"]
Tone = Literal["info", "care", "good", "warn"]


class Source(BaseModel):
    """Where a number or an event comes from: a query (shown verbatim) or record ids in a named table."""

    kind: Literal["sql", "records", "report"]
    label: str
    sql: str | None = None
    table: str | None = None
    ids: list[str] = Field(default_factory=list)


class Insight(BaseModel):
    id: str
    title: str
    reason: str
    tone: Tone = "info"
    source: Source


class Event(BaseModel):
    ts: str
    type: str  # account | case | promise | contact | note | call | recording | hardship | nba | summary | offer | plan
    #            | simulation | signal | merge | review | test | drift | quality
    title: str
    detail: str | None = None
    tone: Tone = "info"
    ref: str | None = None
    table: str | None = None
    link: str | None = None


class Line(BaseModel):
    name: str
    values: list[float | None]


class Series(BaseModel):
    title: str
    unit: Literal["pct", "count", "cad"] = "pct"
    x: list[str]
    lines: list[Line]
    note: str | None = None
    suppressed: int = 0
    source: Source


class Table(BaseModel):
    title: str | None = None
    columns: list[str]
    rows: list[list[str | float | int | bool | None]]
    note: str | None = None
    source: Source


class Fact(BaseModel):
    label: str
    value: str


class Section(BaseModel):
    id: str
    label: str
    kind: Literal["timeline", "series", "table", "facts"]
    intro: str | None = None
    events: list[Event] = Field(default_factory=list)
    series: list[Series] = Field(default_factory=list)
    tables: list[Table] = Field(default_factory=list)
    facts: list[Fact] = Field(default_factory=list)


class Action(BaseModel):
    """A step the person can take. Every write goes through an existing endpoint that writes the audit log."""

    id: str
    kind: Literal["nba", "summary", "hardship_confirm", "hardship_lower", "simulator", "batch_approve",
                  "playbook_approve", "link", "identity_verdict", "drift_approve", "propose_test"]
    label: str
    detail: str | None = None
    endpoint: str | None = None  # the existing endpoint the button calls (method POST)
    link: str | None = None  # an app route
    target: str | None = None
    enabled: bool = True
    why_disabled: str | None = None
    options: list[Fact] = Field(default_factory=list)  # choices (program ids, strategy codes)


class TrackView(BaseModel):
    meta: dict
    kind: Kind
    id: str
    title: str
    subtitle: str | None = None
    badges: list[str] = Field(default_factory=list)
    figures: list[Fact] = Field(default_factory=list)
    insights: list[Insight] = Field(default_factory=list)
    sections: list[Section] = Field(default_factory=list)
    actions: list[Action] = Field(default_factory=list)
    case_id: str | None = None
    golden_id: str | None = None
    aggregates_only: bool = False


class Subject(BaseModel):
    id: str
    label: str
    sublabel: str | None = None
    badges: list[str] = Field(default_factory=list)


class SubjectList(BaseModel):
    kind: Kind
    items: list[Subject]
    note: str | None = None


class KindInfo(BaseModel):
    kind: Kind
    label: str
    hint: str


class Kinds(BaseModel):
    role: str
    kinds: list[KindInfo]
    suggested: Subject | None = None
    suggested_kind: Kind | None = None


class ProposeIn(BaseModel):
    strategy_code: str
    note: str | None = None


class Proposed(BaseModel):
    ok: bool = True
    audit_id: int
    proposal_id: str
    status: str
    note: str
