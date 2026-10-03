"""The only entry point for LLM calls.

complete_json(prompt_id, version, inputs, schema_name) ->
  1. loads llm/prompts/<prompt_id>/v<version>.md and llm/schemas/<schema_name>.json
  2. checks the cache (keyed by provider + prompt + version + inputs hash)
  3. calls the configured provider; on ProviderUnavailable falls back to offline
  4. validates the output against the schema's required keys, logs provider/version/latency
"""

from __future__ import annotations

import json
import logging
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

from common.config import get_settings
from common.hashing import stable_hash
from llm.providers.base import Provider, ProviderUnavailable
from llm.providers.offline import OfflineProvider

log = logging.getLogger(__name__)
HERE = Path(__file__).resolve().parent


@lru_cache
def _provider(name: str) -> Provider:
    if name == "offline":
        return OfflineProvider()
    if name == "gemini":
        from llm.providers.gemini import GeminiProvider

        return GeminiProvider()
    if name == "ollama":
        from llm.providers.ollama import OllamaProvider

        return OllamaProvider()
    raise ValueError(f"Unknown LLM_PROVIDER '{name}'")


def load_prompt(prompt_id: str, version: int) -> str:
    return (HERE / "prompts" / prompt_id / f"v{version}.md").read_text()


def load_schema(schema_name: str) -> dict:
    return json.loads((HERE / "schemas" / f"{schema_name}.json").read_text())


def _check_required(out: dict, schema: dict) -> None:
    missing = [k for k in schema.get("required", []) if k not in out]
    if missing:
        raise ValueError(f"LLM output missing required keys {missing}")


def complete_json(
    prompt_id: str, version: int, inputs: dict[str, Any], schema_name: str, provider: str | None = None
) -> dict:
    s = get_settings()
    name = provider or s.llm_provider
    prompt, schema = load_prompt(prompt_id, version), load_schema(schema_name)
    model = getattr(s, f"{name}_model", None)  # a different model must not reuse another model's cached answer
    key = stable_hash([name, model, prompt_id, version, inputs])
    cache = s.llm_cache_dir / f"{key}.json"
    if cache.exists():
        return json.loads(cache.read_text())

    t0 = time.perf_counter()
    try:
        prov = _provider(name)
        out = prov.complete_json(prompt_id, prompt, inputs, schema)
    except ProviderUnavailable as e:
        log.warning("LLM provider %s unavailable (%s); falling back to offline", name, e)
        prov = _provider("offline")
        out = prov.complete_json(prompt_id, prompt, inputs, schema)
    _check_required(out, schema)
    out = {**out, "_meta": {"provider": prov.name, "prompt_id": prompt_id, "version": version}}
    log.info("llm %s v%s via %s in %.0f ms", prompt_id, version, prov.name, (time.perf_counter() - t0) * 1e3)

    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(out, default=str))
    return out
