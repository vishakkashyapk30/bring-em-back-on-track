"""Runtime settings. Everything is configurable from `.env` (see `.env.example`)."""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    # Data source: `full` = the 13 GB release in data/raw, `sample` = the ~5,000 customer sample committed under
    # data/sample (tools/make_sample.py), `auto` = full when a full warehouse exists, else a built sample warehouse,
    # else the raw release if it is on disk, else the sample. A sample run writes everything under `sample_build_dir`
    # so it can never overwrite a full-data build.
    data_source: str = "auto"  # auto | full | sample (resolved to full | sample after validation)
    sample_dir: Path = ROOT / "data" / "sample" / "maple_collections_sample"
    sample_build_dir: Path = ROOT / "data" / "sample_build"
    release_dir: Path | None = None  # the folder with data/, files/, labels/, schema/ (derived from data_source)
    artefacts_dir: Path | None = None  # trained promise-break model (derived)
    deliverables_dir: Path | None = None  # benchmark_answers.csv (derived)
    quality_report_md: Path | None = None  # docs/data_quality_report.md (derived)

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

    @property
    def is_sample(self) -> bool:
        return self.data_source == "sample"

    @model_validator(mode="after")
    def _resolve_source(self) -> Settings:
        self.data_source = (self.data_source or "auto").strip().lower()  # an empty DATA_SOURCE (compose default) = auto
        if self.data_source not in ("auto", "full", "sample"):
            raise ValueError(f"DATA_SOURCE must be auto, full or sample, not {self.data_source!r}")
        full_release = self.raw_dir / "maple_collections_release"
        if self.data_source == "auto":
            if self.warehouse_path.exists():
                self.data_source = "full"
            elif (self.sample_build_dir / "warehouse.duckdb").exists():
                self.data_source = "sample"
            else:
                self.data_source = "full" if (full_release / "README.md").exists() else "sample"
        if self.is_sample:
            b = self.sample_build_dir
            derived = {"data_dir": b, "bronze_dir": b / "bronze", "silver_dir": b / "silver",
                       "features_dir": b / "features", "warehouse_path": b / "warehouse.duckdb",
                       "ops_db_path": b / "ops.db", "lancedb_dir": b / "lancedb", "llm_cache_dir": b / "llm_cache",
                       "reports_dir": b / "reports"}
            for k, v in derived.items():
                if k not in self.model_fields_set:
                    setattr(self, k, v)
        if self.release_dir is None:
            self.release_dir = self.sample_dir if self.is_sample else full_release
        if self.artefacts_dir is None:
            self.artefacts_dir = (self.sample_build_dir / "artefacts" if self.is_sample
                                  else ROOT / "models" / "ptp_break" / "artefacts")
        if self.deliverables_dir is None:
            self.deliverables_dir = self.sample_build_dir / "deliverables" if self.is_sample else ROOT / "deliverables"
        if self.quality_report_md is None:
            self.quality_report_md = (self.sample_build_dir / "data_quality_report.md" if self.is_sample
                                      else ROOT / "docs" / "data_quality_report.md")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
