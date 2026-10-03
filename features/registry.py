"""Load + validate features/registry.yaml."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel

from common.protected import assert_no_protected

REGISTRY = Path(__file__).with_name("registry.yaml")


class FeatureSpec(BaseModel):
    name: str
    entity: str
    type: str
    built_by: str
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
    label_accuracy: dict | None = None


def load_registry(path: Path = REGISTRY) -> list[FeatureSpec]:
    specs = [FeatureSpec.model_validate(x) for x in yaml.safe_load(path.read_text())]
    assert_no_protected([s.name for s in specs], "features/registry.yaml")
    return specs
