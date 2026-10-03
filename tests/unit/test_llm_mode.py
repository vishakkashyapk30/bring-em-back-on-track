"""The per-request switch between rules and a language model."""

from common import llm_mode
from common.config import get_settings


def test_rules_mode_forces_the_offline_provider(monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_provider", "ollama")
    assert llm_mode.effective_provider() == "ollama"
    with llm_mode.use_mode("rules"):
        assert llm_mode.effective_provider() == "offline"
    with llm_mode.use_mode("llm"):
        assert llm_mode.effective_provider() == "ollama"
    assert llm_mode.requested_mode() is None


def test_unknown_mode_is_ignored(monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_provider", "offline")
    with llm_mode.use_mode("banana"):
        assert llm_mode.requested_mode() is None


def test_availability_says_why_when_no_model_is_configured(monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_provider", "offline")
    llm_mode._cache.clear()
    info = llm_mode.availability()
    assert info["available"] is False and "LLM_PROVIDER=offline" in info["reason"]


def test_rules_mode_makes_ask_skip_the_model(monkeypatch):
    from nlq.rewrite import choose_metric

    monkeypatch.setattr(get_settings(), "llm_provider", "ollama")
    with llm_mode.use_mode("rules"):
        assert choose_metric("What proportion of the people we phoned actually reached the right person?") is None
