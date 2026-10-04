"""'Waiting for you' inbox: every pending human review for the signed-in person, read-only, with a link to the screen
where they act on it (docs/inbox_and_watchlist.md)."""

from __future__ import annotations

from pydantic import BaseModel


class InboxItem(BaseModel):
    id: str
    type: str
    title: str                       # what it is
    reason: str                      # why it needs this person, in plain English
    age_days: int | None = None      # days waiting (ops items: since created; warehouse items: since the data date)
    age_label: str
    due: str | None = None           # review deadline, when there is one
    overdue: bool = False
    link: str                        # the existing screen where it is approved
    subject_kind: str | None = None  # for the watch button: customer | case | agent | employer | ...
    subject_id: str | None = None


class InboxGroup(BaseModel):
    type: str
    label: str
    why: str
    count: int                       # all pending in scope (items holds the first few)
    items: list[InboxItem]
    link: str
    link_label: str
    informational: bool = False      # shown, not counted (an analyst's own proposals)


class NotAvailable(BaseModel):
    source: str
    reason: str


class InboxResponse(BaseModel):
    role: str
    total: int                       # to look at now: each group counts at most its first few items
    backlog: int = 0                 # everything pending in scope (can be tens of thousands for some roles)
    groups: list[InboxGroup]
    top: list[InboxItem]
    not_available: list[NotAvailable]
    as_of: str
    note: str | None = None


class InboxCounts(BaseModel):
    role: str
    total: int
    backlog: int = 0
    by_type: dict[str, int]
