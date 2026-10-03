"""Assertion helpers shared by the spec tests (behaviour-level only)."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from tests_spec import spec_constants as C
from tests_spec.adapter import Action, ActionResult, NbaDecision


def is_pressure(action: Action) -> bool:
    return action.treatment in C.PRESSURE_TREATMENTS


def contacts_customer(action: Action) -> bool:
    return action.treatment != "no_contact"


def has_label(text: str | None, *labels: str) -> bool:
    t = (text or "").lower()
    return any(lbl.lower() in t for lbl in labels)


def assert_denied(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
    """Forbidden = raises PermissionError, or returns ActionResult(allowed=False)."""
    try:
        result = fn(*args, **kwargs)
    except PermissionError:
        return
    assert isinstance(result, ActionResult), f"expected denial, got {result!r}"
    assert result.allowed is False, f"expected denial, got {result!r}"


def assert_allowed(result: Any) -> None:
    if isinstance(result, ActionResult):
        assert result.allowed, f"expected the action to be allowed: {result!r}"


def decision_signature(d: NbaDecision) -> tuple:
    """Everything a customer-facing decision consists of, for invariance tests."""
    a = d.action
    return (
        a.treatment,
        a.channel,
        a.window,
        a.program_id,
        None if d.break_probability is None else round(d.break_probability, 9),
        d.review_mode,
        d.route_to,
        tuple(d.explanation.rules_applied),
        tuple(d.explanation.risk_reasons),
        d.explanation.text,
    )


def word_count(text: str) -> int:
    return len(re.findall(r"\S+", text or ""))


PAN_PATTERN = re.compile(r"\b(?:\d[ -]?){13,19}\b")
