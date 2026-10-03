"""Per-source parsing of names, DOBs (4 formats), phones and postal codes before matching."""

from __future__ import annotations


def parse_name(raw: str | None) -> dict[str, str | None]:
    """'R. MITCHELL' / 'MITCHELL, RYAN JAMES' -> {first, middle, last, initial}. TODO(WS-A)."""
    raise NotImplementedError


def parse_dob(raw: str | None) -> tuple[str | None, bool]:
    """Return (ISO date, ambiguous_day_month flag). TODO(WS-A): the 4 formats seen in profiling."""
    raise NotImplementedError


def normalise_phone(raw: str | None) -> str | None:
    """E.164 (+1XXXXXXXXXX); partly masked card phones keep only the visible digits. TODO(WS-A)."""
    raise NotImplementedError
