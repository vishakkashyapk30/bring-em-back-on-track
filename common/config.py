"""Runtime settings. Everything is configurable from `.env` (see `.env.example`)."""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    # Paths
    data_dir: Path = ROOT / "data"
    raw_dir: Path = ROOT / "data" / "raw"
    bronze_dir: Path = ROOT / "data" / "bronze"
    silver_dir: Path = ROOT / "data" / "silver"
    features_dir: Path = ROOT / "data" / "features"
    warehouse_path: Path = ROOT / "data" / "warehouse.duckdb"
    ops_db_path: Path = ROOT / "data" / "ops.db"
    lancedb_dir: Path = ROOT / "data" / "lancedb"
    reports_dir: Path = ROOT / "reports"

    # Business constants
    as_of_date: date = date(2026, 9, 28)  # dictionary snapshot date
    suppression_min_group: int = 10  # hide groups smaller than this in aggregates
    freshness_sla_hours: int = 26  # contract rule 9
    hardship_review_business_days: int = 5  # D11, TBC policy

    # LLM (D13): offline is the default and must always work
    llm_provider: str = "offline"  # offline | openai | anthropic | gemini | deepseek | ollama (the primary)
    llm_fallback: str = "ollama"  # tried when the primary is down or over quota; then the deterministic rules
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    llm_min_interval_sec: float = 6.5  # spacing between cloud calls; 6.5 s keeps the free Gemini tier under 10 a minute
    deepseek_api_key: str | None = None
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com"
    openai_api_key: str | None = None
    openai_model: str = "gpt-6-luna"
    openai_base_url: str = "https://api.openai.com/v1"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-haiku-4-5-20251001"
    anthropic_base_url: str = "https://api.anthropic.com"
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "TBC"
    llm_cache_dir: Path = ROOT / "data" / "llm_cache"

    # API
    use_fixtures: bool = True  # serve api/fixtures/*.json for endpoints whose module isn't real yet
    force_fixtures: bool = False  # serve fixtures even when a warehouse exists (offline demos, tests)
    session_secret: str = "dev-only-change-me"
    cors_origins: str = "http://localhost:5173"


@lru_cache
def get_settings() -> Settings:
    return Settings()
