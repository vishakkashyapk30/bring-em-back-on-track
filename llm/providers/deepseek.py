"""DeepSeek over its OpenAI-style chat API. Set DEEPSEEK_API_KEY and DEEPSEEK_MODEL (default deepseek-chat) in .env."""

from __future__ import annotations

from typing import Any

import httpx

from common.config import get_settings
from llm.providers.base import Provider, ProviderUnavailable
from llm.providers.gemini import parse_json, post_with_retry, prompt_with_schema


class DeepSeekProvider(Provider):
    name = "deepseek"

    def __init__(self) -> None:
        s = get_settings()
        if not s.deepseek_api_key:
            raise ProviderUnavailable("Set DEEPSEEK_API_KEY in .env")
        self._key, self._model, self._base = s.deepseek_api_key, s.deepseek_model, s.deepseek_base_url.rstrip("/")

    def complete_json(self, prompt_id: str, prompt: str, inputs: dict[str, Any], schema: dict) -> dict:
        body = {"model": self._model, "temperature": 0, "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": "You return one JSON object and nothing else."},
                             {"role": "user", "content": prompt_with_schema(prompt, inputs, schema)}]}
        try:
            with httpx.Client(timeout=90) as c:
                headers = {"Authorization": f"Bearer {self._key}"}
                r = post_with_retry(c, f"{self._base}/chat/completions", headers=headers, json=body)
            r.raise_for_status()
            return parse_json(r.json()["choices"][0]["message"]["content"])
        except Exception as e:  # noqa: BLE001
            raise ProviderUnavailable(f"deepseek call failed: {type(e).__name__}: {str(e)[:200]}") from e
