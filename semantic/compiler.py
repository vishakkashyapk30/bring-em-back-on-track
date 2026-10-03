"""Compile question tokens -> SQL against role views.

MetricFlow if it compiles against dbt-duckdb, else this in-house compiler.
"""

from __future__ import annotations

from nlq.schemas import QueryTokens


def compile_tokens(tokens: QueryTokens, role: str) -> str:
    """Return SQL for a certified metric. Raise NoMetricMatch if no metric fits. TODO(WS-B)."""
    raise NotImplementedError


class NoMetricMatch(Exception):
    pass
