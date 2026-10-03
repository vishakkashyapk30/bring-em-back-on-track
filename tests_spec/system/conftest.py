"""System fixtures: a seeded system after the nightly run, and signed-in sessions per persona.

Users (synthetic): agent-001 (team-a, owns Ryan's case), agent-002 (team-b), spec-001 (hardship
specialist), lead-001 (team lead, team-a), analyst-001, steward-001.
"""

from __future__ import annotations

import pytest

from tests_spec import factories as F

USERS = {
    "agent": ("agent-001", "team-a"),
    "agent_other": ("agent-002", "team-b"),
    "hardship_specialist": ("spec-001", "team-h"),
    "team_lead": ("lead-001", "team-a"),
    "analyst": ("analyst-001", None),
    "data_steward": ("steward-001", None),
}


@pytest.fixture
def seeded(system):
    system.seed(F.ryan_mitchell_tables())
    system.run_nightly(F.AS_OF)
    return system


@pytest.fixture
def login(seeded):
    """login("agent") -> Session. Use "agent_other" for a second agent on another team."""

    def _login(who: str):
        user_id, team = USERS[who]
        role = "agent" if who == "agent_other" else who
        return seeded.login(user_id, role, team)

    return _login


@pytest.fixture
def ryan_gid(login):
    gid = login("agent").find_customer("crm", "RYM-1142")
    assert gid
    return gid


@pytest.fixture
def ryan_item(login):
    items = [i for i in login("agent").work_queue() if i.case_id == "CASE-RYM-0001"]
    assert items, "Ryan's open case must be in his assigned agent's queue"
    return items[0]
