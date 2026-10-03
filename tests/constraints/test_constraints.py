"""Constraint tests for the hard rules (protected attributes, policy gate, hardship latch, explanations,
suppression, freshness, audit). `todo`-marked tests are skipped until their module lands;
remove the marker when you implement the module. Run them all with `pytest -m todo`."""

import re
from pathlib import Path

import pytest

from common.protected import FORBIDDEN
from features.registry import load_registry

ROOT = Path(__file__).resolve().parents[2]


def test_no_protected_attributes_in_features_semantic_prompts():
    load_registry()  # raises on protected names
    scanned = list((ROOT / "llm" / "prompts").rglob("*.md")) + list((ROOT / "semantic").rglob("*.yaml"))
    for p in scanned:
        text = p.read_text().lower()
        hits = [a for a in FORBIDDEN if re.search(rf"\b{a}\b", text)]
        assert not hits, f"{p} mentions {hits}"


def test_no_wide_m01_m12_columns_in_training():
    from models.ptp_break.dataset import check_columns

    with pytest.raises(ValueError):
        check_columns(["dpd", "dpd_m01"])


@pytest.mark.todo
def test_policy_gate_blocks_cease_insolvency_deceased():
    raise NotImplementedError("implement the module, then this test")


@pytest.mark.todo
def test_gate_respects_permitted_hours_timezone_sunday_holiday_cap():
    raise NotImplementedError("implement the module, then this test")


@pytest.mark.todo
def test_hardship_possible_removes_pressure_treatments():
    raise NotImplementedError("implement the module, then this test")


@pytest.mark.todo
def test_every_nba_has_explanation_with_rules_and_drivers():
    raise NotImplementedError("implement the module, then this test")


@pytest.mark.todo
def test_suppression_under_10():
    raise NotImplementedError("implement the module, then this test")


@pytest.mark.todo
def test_stale_feature_blocks_decision():
    raise NotImplementedError("implement the module, then this test")


@pytest.mark.todo
def test_every_write_creates_audit_row():
    raise NotImplementedError("implement the module, then this test")
