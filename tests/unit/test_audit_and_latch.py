import sqlite3

import pytest

from common.config import get_settings
from common.types import HardshipLevel
from governance import audit, hardship_latch


def test_audit_append_only():
    aid = audit.record("u1", "agent", "nba_decision", "case", "CS-1", {"a": 1}, {"b": 2})
    assert aid == 1
    con = sqlite3.connect(get_settings().ops_db_path)
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("DELETE FROM audit_log")


def test_model_cannot_lower_hardship():
    with pytest.raises(hardship_latch.LatchError):
        hardship_latch.transition("G-1", HardshipLevel.possible, HardshipLevel.none, "model", "sys", "agent",
                                  reason="auto")


def test_specialist_lowers_with_reason():
    aid = hardship_latch.transition("G-1", HardshipLevel.possible, HardshipLevel.none, "specialist", "HS-1",
                                    "hardship_specialist", reason="Income restored, verified")
    assert aid > 0


def test_lowering_needs_reason():
    with pytest.raises(hardship_latch.LatchError):
        hardship_latch.transition("G-1", HardshipLevel.clear, HardshipLevel.none, "specialist", "HS-1",
                                  "hardship_specialist")
