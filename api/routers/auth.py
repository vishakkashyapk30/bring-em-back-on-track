from fastapi import APIRouter, Depends, Response

from api.deps import COOKIE, current_session, sign
from api.personas import DEMO_USERS
from api.schemas.common import Session

router = APIRouter(tags=["auth"])


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
