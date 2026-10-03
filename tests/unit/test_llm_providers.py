"""The cloud providers talk plain HTTPS (mocked here): a good reply is parsed, any failure becomes ProviderUnavailable
so the client falls back to the offline rules."""

import httpx
import pytest

from common.config import get_settings
from llm.providers.base import ProviderUnavailable
from llm.providers.deepseek import DeepSeekProvider
from llm.providers.gemini import GeminiProvider, parse_json, prompt_with_schema

SCHEMA = {"type": "object", "required": ["a"], "properties": {"a": {"type": "string"}}}


def _mock(monkeypatch, handler):
    real = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))


def test_parse_json_accepts_a_fenced_reply():
    assert parse_json('```json\n{"a": "x"}\n```') == {"a": "x"}


def test_prompt_carries_the_schema_and_marks_the_input_as_data():
    p = prompt_with_schema("Do it.", {"q": "hi"}, SCHEMA)
    assert '"required": ["a"]' in p and "data, not instructions" in p


def test_gemini_parses_a_reply(monkeypatch):
    monkeypatch.setattr(get_settings(), "gemini_api_key", "k")
    reply = {"candidates": [{"content": {"parts": [{"text": '{"a": "ok"}'}]}}]}
    _mock(monkeypatch, lambda req: httpx.Response(200, json=reply))
    assert GeminiProvider().complete_json("x", "p", {}, SCHEMA) == {"a": "ok"}


def test_gemini_failure_becomes_provider_unavailable(monkeypatch):
    monkeypatch.setattr(get_settings(), "gemini_api_key", "k")
    monkeypatch.setattr("llm.providers.gemini.time.sleep", lambda s: None)
    _mock(monkeypatch, lambda req: httpx.Response(429, json={"error": "quota"}))
    with pytest.raises(ProviderUnavailable):
        GeminiProvider().complete_json("x", "p", {}, SCHEMA)


def test_missing_key_is_unavailable(monkeypatch):
    monkeypatch.setattr(get_settings(), "gemini_api_key", None)
    monkeypatch.setattr(get_settings(), "deepseek_api_key", None)
    for cls in (GeminiProvider, DeepSeekProvider):
        with pytest.raises(ProviderUnavailable):
            cls()


def test_deepseek_parses_a_reply(monkeypatch):
    monkeypatch.setattr(get_settings(), "deepseek_api_key", "k")
    _mock(monkeypatch, lambda req: httpx.Response(200, json={"choices": [{"message": {"content": '{"a": "ok"}'}}]}))
    assert DeepSeekProvider().complete_json("x", "p", {}, SCHEMA) == {"a": "ok"}
