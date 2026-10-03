"""Run guarded SQL on a READ-ONLY DuckDB connection limited to the role's views (D5)."""

from __future__ import annotations

from typing import Any


def execute(sql: str, role: str) -> tuple[list[str], list[list[Any]]]:
    raise NotImplementedError("TODO(WS-B): common.db.warehouse(read_only=True); small-group suppression")
