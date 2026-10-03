from fastapi import APIRouter, Depends, Response

from api.deps import COOKIE, current_session, sign
from api.schemas.common import Session

router = APIRouter(tags=["auth"])

DEMO_USERS = {  # demo personas
    "agent": Session(user_id="AG-6274", role="agent", team_id="CGY-MID-2", display_name="M. Cochran"),
    "hardship_specialist": Session(user_id="AG-5633", role="hardship_specialist", team_id="MTL-HARD-2",
                                   display_name="C. Leblanc"),
    "team_lead": Session(user_id="AG-9065", role="team_lead", team_id="CGY-MID-2", display_name="C. Burgess"),
    "analyst": Session(user_id="AN-0003", role="analyst", display_name="S. Tremblay"),
    "steward": Session(user_id="DS-0001", role="steward", display_name="K. Nguyen"),
}


@router.post("/auth/session")
def login(role: str, response: Response) -> Session:
    s = DEMO_USERS[role]
    response.set_cookie(COOKIE, sign(s), httponly=True, samesite="lax")
    return s


@router.post("/auth/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(COOKIE)
    return {"ok": True}


@router.get("/me")
def me(session: Session = Depends(current_session)) -> Session:
    return session
