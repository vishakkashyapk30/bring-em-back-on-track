"""Role checks for API routes. Demo auth = signed cookie; production = SSO groups."""

from common.types import Role

ALL = set(Role)
AGENT_PLUS = {Role.agent, Role.hardship_specialist, Role.team_lead}
ANALYTICS = {Role.analyst, Role.team_lead}
GOVERNANCE = {Role.steward, Role.analyst, Role.team_lead}
