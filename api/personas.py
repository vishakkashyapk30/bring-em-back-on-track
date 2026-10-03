"""The five demo personas, taken from real agents in the data. A session cookie is only honoured if it matches one of
these, so a cookie from an older build (made-up names) can't keep a stale identity signed in."""

from api.schemas.common import Session

DEMO_USERS = {
    "agent": Session(user_id="AG-6274", role="agent", team_id="CGY-MID-2", display_name="M. Cochran"),
    "hardship_specialist": Session(user_id="AG-5633", role="hardship_specialist", team_id="MTL-HARD-2",
                                   display_name="C. Leblanc"),
    "team_lead": Session(user_id="AG-9065", role="team_lead", team_id="CGY-MID-2", display_name="C. Burgess"),
    "analyst": Session(user_id="AN-0003", role="analyst", display_name="S. Tremblay"),
    "steward": Session(user_id="DS-0001", role="steward", display_name="K. Nguyen"),
}


def is_current(s: Session) -> bool:
    return DEMO_USERS.get(s.role) == s
