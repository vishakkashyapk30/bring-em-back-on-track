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
from common.llm_mode import effective_provider
from llm.providers.base import Provider, ProviderUnavailable
from llm.providers.offline import OfflineProvider

log = logging.getLogger(__name__)
HERE = Path(__file__).resolve().parent


@lru_cache
def _provider(name: str) -> Provider:
    if name == "offline":
        return OfflineProvider()
    if name == "openai":
        from llm.providers.openai import OpenAIProvider

        return OpenAIProvider()
    if name == "anthropic":
        from llm.providers.anthropic import AnthropicProvider

        return AnthropicProvider()
    if name == "gemini":
        from llm.providers.gemini import GeminiProvider

        return GeminiProvider()
    if name == "deepseek":
        from llm.providers.deepseek import DeepSeekProvider

        return DeepSeekProvider()
    if name == "ollama":
        from llm.providers.ollama import OllamaProvider

        return OllamaProvider()
    raise ValueError(f"Unknown LLM_PROVIDER '{name}'")


_down: dict[str, float] = {}  # provider -> time until which it is skipped after a failure (circuit breaker)
DOWN_FOR_S = 90.0


def chain(primary: str) -> list[str]:
    """Providers to try in order: the configured one (the paid API in production), then LLM_FALLBACK (a local model,
    ollama by default), then offline rules, which always answer. `offline` alone stays offline."""
    s = get_settings()
    if primary == "offline":
        return ["offline"]
    out = [primary]
    for extra in (s.llm_fallback or "").replace(" ", "").split(","):
        if extra and extra not in out and extra != "offline":
            out.append(extra)
    return [*out, "offline"]


def _is_down(name: str) -> bool:
    return _down.get(name, 0.0) > time.time()


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
    name = provider or effective_provider()
    prompt, schema = load_prompt(prompt_id, version), load_schema(schema_name)
    model = getattr(s, f"{name}_model", None)  # a different model must not reuse another model's cached answer
    key = stable_hash([name, model, prompt_id, version, inputs])
    cache = s.llm_cache_dir / f"{key}.json"
    if cache.exists():
        return json.loads(cache.read_text())

    t0 = time.perf_counter()
    prov, out = None, None
    for cand in chain(name):
        if cand != "offline" and _is_down(cand):
            continue
        try:
            prov = _provider(cand)
            out = prov.complete_json(prompt_id, prompt, inputs, schema)
            break
        except (ProviderUnavailable, ValueError) as e:  # unreachable, quota, or unusable output: next in the chain
            if cand == "offline":
                raise
            _down[cand] = time.time() + DOWN_FOR_S
            log.warning("LLM provider %s unavailable (%s); trying the next one", cand, e)
    _check_required(out, schema)
    out = {**out, "_meta": {"provider": prov.name, "prompt_id": prompt_id, "version": version}}
    log.info("llm %s v%s via %s in %.0f ms", prompt_id, version, prov.name, (time.perf_counter() - t0) * 1e3)

    if prov.name == name or name == "offline":  # an answer from a fallback is not cached under the primary's key
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(out, default=str))
    return out
