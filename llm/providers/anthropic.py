"""Claude over the Anthropic Messages API (REST, no SDK). Set ANTHROPIC_API_KEY and ANTHROPIC_MODEL in .env."""

from __future__ import annotations

from typing import Any

import httpx

from common.config import get_settings
from llm.providers.base import Provider, ProviderUnavailable
from llm.providers.gemini import parse_json, post_with_retry, prompt_with_schema


class AnthropicProvider(Provider):
    name = "anthropic"

    def __init__(self) -> None:
        s = get_settings()
        if not s.anthropic_api_key:
            raise ProviderUnavailable("Set ANTHROPIC_API_KEY in .env")
        self._key, self._model, self._base = s.anthropic_api_key, s.anthropic_model, s.anthropic_base_url.rstrip("/")

    def complete_json(self, prompt_id: str, prompt: str, inputs: dict[str, Any], schema: dict) -> dict:
        body = {"model": self._model, "max_tokens": 4096,
                "system": "You return one JSON object and nothing else.",
                "messages": [{"role": "user", "content": prompt_with_schema(prompt, inputs, schema)}]}
        headers = {"x-api-key": self._key, "anthropic-version": "2023-06-01"}
        try:
            with httpx.Client(timeout=120) as c:
                r = post_with_retry(c, f"{self._base}/v1/messages", headers=headers, interval=0.0, json=body)
            r.raise_for_status()
            text = "".join(b.get("text", "") for b in r.json()["content"] if b.get("type") == "text")
            return parse_json(text)
        except Exception as e:  # noqa: BLE001
            raise ProviderUnavailable(f"anthropic call failed: {type(e).__name__}: {str(e)[:200]}") from e
