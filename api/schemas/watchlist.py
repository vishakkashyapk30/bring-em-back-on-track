"""Saved watchlist: subjects a person pins to follow, with what changed since they last looked."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Kind = Literal["customer", "case", "agent", "employer", "cohort", "data_product", "identity"]


class PinIn(BaseModel):
    kind: Kind
    subject_id: str = Field(min_length=1, max_length=200)
    label: str | None = Field(default=None, max_length=200)


class Pin(BaseModel):
    kind: Kind
    subject_id: str


class WatchItem(BaseModel):
    kind: Kind
    subject_id: str
    label: str
    created_at: str
    last_seen_at: str
    link: str                    # the existing screen for the subject
    track_link: str | None = None  # /track/<kind>/<id> (used when the Track pages are present)
    status: str                  # the facts now, one line
    changes: list[str]           # what changed since last_seen_at; empty when nothing did
    available: bool = True       # False when you can no longer open the subject (the reason is in status)


class WatchList(BaseModel):
    items: list[WatchItem]
    changed: int


class PinResult(BaseModel):
    ok: bool = True
    audit_id: int | None = None  # None when nothing changed (already pinned / not pinned)
    pinned: bool
    kind: Kind
    subject_id: str
