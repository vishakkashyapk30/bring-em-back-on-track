"""Fixture loader. Until a module is real, API routers return `api/fixtures/<name>.json` (use_fixtures=True)."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).resolve().parent.parent / "api" / "fixtures"


@lru_cache
def fixture(name: str) -> Any:
    return json.loads((FIXTURES / f"{name}.json").read_text())
