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
    llm_provider: str = "offline"  # offline | gemini | ollama
    gemini_api_key: str | None = None
    gemini_model: str = "TBC"
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
