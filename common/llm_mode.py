"""Per-request choice between deterministic rules and a language model.

The API sets the mode for the request being served (`rules` or `llm`); code that may call a language model asks
`effective_provider()` instead of reading the setting, so a user can switch the same question between the two.
`rules` always forces the offline provider. `llm` uses the configured provider (LLM_PROVIDER); if none is configured,
or it is unreachable, the answer falls back to rules and says so. With no mode set, the setting decides.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from contextvars import ContextVar

from common.config import get_settings

_mode: ContextVar[str | None] = ContextVar("llm_mode", default=None)
_cache: dict[str, tuple[float, dict]] = {}


@contextmanager
def use_mode(mode: str | None):
    """`with use_mode("rules"): ...` for the code inside the block (and anything it calls)."""
    token = _mode.set(mode if mode in ("rules", "llm") else None)
    try:
        yield
    finally:
        _mode.reset(token)


def requested_mode() -> str | None:
    return _mode.get()


def effective_provider() -> str:
    """The provider name to use right now: offline when the user chose rules, else the configured one."""
    if _mode.get() == "rules":
        return "offline"
    return get_settings().llm_provider


def _probe(provider: str) -> dict:
    s = get_settings()
    info = {"provider": provider, "model": None, "available": False, "reason": ""}
    if provider == "offline":
        info["reason"] = "No language model is configured on this server (LLM_PROVIDER=offline)."
    elif provider == "ollama":
        info["model"] = s.ollama_model
        try:
            import httpx

            names = [m["name"] for m in httpx.get(f"{s.ollama_host}/api/tags", timeout=1.5).json().get("models", [])]
            base = s.ollama_model.split(":")[0]
            info["available"] = s.ollama_model in names or any(n.startswith(base) for n in names)
            if not info["available"]:
                info["reason"] = f"Ollama is running but the model {s.ollama_model} is not installed."
        except Exception:  # noqa: BLE001 - not reachable
            info["reason"] = "The local language model (Ollama) is not reachable."
    elif provider == "deepseek":
        info["model"] = s.deepseek_model
        info["available"] = bool(s.deepseek_api_key)
        if not info["available"]:
            info["reason"] = "No DeepSeek API key is set."
    elif provider == "openai":
        info["model"] = s.openai_model
        info["available"] = bool(s.openai_api_key)
        if not info["available"]:
            info["reason"] = "No OpenAI API key is set."
    elif provider == "anthropic":
        info["model"] = s.anthropic_model
        info["available"] = bool(s.anthropic_api_key)
        if not info["available"]:
            info["reason"] = "No Anthropic API key is set."
    elif provider == "gemini":
        info["model"] = s.gemini_model
        info["available"] = bool(s.gemini_api_key)
        if not info["available"]:
            info["reason"] = "No Gemini API key is set."
    return info


def availability() -> dict:
    """What the switch can offer: {provider, model, available, reason}. The configured provider first, then the
    fallback (LLM_FALLBACK, a local model), then none (rules). Cached for 30 s (it may probe Ollama)."""
    s = get_settings()
    key = f"{s.llm_provider}>{s.llm_fallback}"
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < 30:
        return hit[1]
    info = _probe(s.llm_provider)
    if not info["available"] and s.llm_provider != "offline":
        for extra in (s.llm_fallback or "").replace(" ", "").split(","):
            if extra and extra not in ("offline", s.llm_provider):
                alt = _probe(extra)
                if alt["available"]:
                    alt["reason"] = f"{info['reason']} Using the fallback model {alt['model']} instead.".strip()
                    info = alt
                    break
    _cache[key] = (time.time(), info)
    return info
