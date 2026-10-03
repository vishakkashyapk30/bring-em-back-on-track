"""Load + validate features/registry.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

from common.protected import assert_no_protected

REGISTRY = Path(__file__).with_name("registry.yaml")


class FeatureSpec(BaseModel):
    name: str
    entity: str
    type: str
    built_by: Literal["sql", "ai", "voice"]
    source: list[str]
    definition: str
    available_ts: str
    refresh: str
    freshness_sla_hours: int
    owner: str
    version: int
    fairness_review: str
    description: str | None = None
    prompt: str | None = None
    prompt_version: int | None = None
    provider: str | None = None  # AI features: offline (rules) or the optional language-model provider
    label_accuracy: dict | None = None


def load_registry(path: Path = REGISTRY) -> list[FeatureSpec]:
    specs = [FeatureSpec.model_validate(x) for x in yaml.safe_load(path.read_text())]
    assert_no_protected([s.name for s in specs], "features/registry.yaml")
    for s in specs:
        if s.built_by == "ai" and not (s.prompt and s.prompt_version and s.label_accuracy):
            raise ValueError(f"{s.name}: an AI feature needs prompt, prompt_version and label_accuracy")
    return specs
