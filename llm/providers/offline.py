"""Deterministic offline provider (the default). Each prompt_id maps to a rule/template implementation.

The real logic lives next to the feature that needs it (e.g. features/text_rules.py, nlq/parser.py);
this module only routes to it, so the system works with LLM_PROVIDER=offline (D13).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from llm.providers.base import Provider

Handler = Callable[[dict[str, Any]], dict]
_HANDLERS: dict[str, Handler] = {}


def register(prompt_id: str) -> Callable[[Handler], Handler]:
    def deco(fn: Handler) -> Handler:
        _HANDLERS[prompt_id] = fn
        return fn

    return deco


class OfflineProvider(Provider):
    name = "offline"

    def complete_json(self, prompt_id: str, prompt: str, inputs: dict[str, Any], schema: dict) -> dict:
        try:
            handler = _HANDLERS[prompt_id]
        except KeyError as e:
            raise NotImplementedError(
                f"No offline handler registered for prompt '{prompt_id}'. Every LLM use needs one."
            ) from e
        return handler(inputs)
