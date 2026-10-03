from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Provider(ABC):
    name: str

    @abstractmethod
    def complete_json(self, prompt_id: str, prompt: str, inputs: dict[str, Any], schema: dict) -> dict:
        """Return a dict that validates against `schema`."""


class ProviderUnavailable(RuntimeError):
    """Raised when a provider isn't configured or is rate-limited; the client falls back to offline."""
