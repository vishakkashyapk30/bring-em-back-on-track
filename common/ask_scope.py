"""What the signed-in person may get from Ask, decided BEFORE anything runs (SQL, retrieval or a language model).

The API sets the scope for the request; nlq.pipeline checks it at the points where data would be read. The scope is the
same in rules mode and language-model mode: choosing a model never widens what a role can see.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

METRICS_DENIED = ("Refused: portfolio metrics are available to analysts and team leads. "
                  "Agents see their own customers in the customer view.")


@dataclass
class AskScope:
    allow_metrics: bool = True
    # May this role open the call summary of this case? None = any case (no signed-in scope, e.g. batch jobs).
    case_allowed: Callable[[str], bool] | None = None
    case_denied_reason: str = "Refused: you can only open call summaries for cases you are responsible for."


_scope: ContextVar[AskScope | None] = ContextVar("ask_scope", default=None)


@contextmanager
def use_scope(scope: AskScope | None):
    token = _scope.set(scope)
    try:
        yield
    finally:
        _scope.reset(token)


def current() -> AskScope | None:
    return _scope.get()
