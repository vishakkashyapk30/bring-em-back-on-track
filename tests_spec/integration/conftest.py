"""Integration fixtures: Ryan Mitchell's synthetic sources loaded and the nightly pipeline run."""

from __future__ import annotations

import pytest

from tests_spec import factories as F


@pytest.fixture
def ryan_tables():
    return F.ryan_mitchell_tables()


@pytest.fixture
def loaded_with_report(adapter, ryan_tables):
    """(adapter, quality report) after loading Ryan + Lakeshore cohort and running the nightly build."""
    adapter.load_sources(ryan_tables)
    report = adapter.run_pipeline(F.AS_OF)
    return adapter, report


@pytest.fixture
def loaded(loaded_with_report):
    """Adapter with Ryan + Lakeshore cohort loaded and the nightly build done as of AS_OF."""
    return loaded_with_report[0]


@pytest.fixture
def ryan_gid(loaded):
    gid = loaded.find_golden_id("crm", "RYM-1142")
    assert gid, "Ryan's CRM record must resolve to a golden ID"
    return gid
