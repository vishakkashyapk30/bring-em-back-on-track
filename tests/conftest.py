import pytest


@pytest.fixture(autouse=True)
def _isolated_ops_db(tmp_path, monkeypatch):
    """Every test gets its own ops.db and LLM cache; offline LLM provider."""
    monkeypatch.setenv("OPS_DB_PATH", str(tmp_path / "ops.db"))
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path / "llm_cache"))
    monkeypatch.setenv("LLM_PROVIDER", "offline")
    from common.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
