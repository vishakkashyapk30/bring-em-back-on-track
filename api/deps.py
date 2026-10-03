"""Session + role dependencies. Demo auth: HMAC-signed cookie {user_id, role, team_id}."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from collections.abc import Callable, Iterable

from fastapi import Cookie, Depends, HTTPException

from api.schemas.common import Session
from common.config import get_settings
from common.fixtures import fixture
from common.types import Role

COOKIE = "c360_session"


def sign(session: Session) -> str:
    body = base64.urlsafe_b64encode(session.model_dump_json().encode()).decode()
    mac = hmac.new(get_settings().session_secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{mac}"


def unsign(token: str) -> Session:
    body, _, mac = token.rpartition(".")
    good = hmac.new(get_settings().session_secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(mac, good):
        raise HTTPException(401, "Invalid session")
    return Session.model_validate(json.loads(base64.urlsafe_b64decode(body)))


def current_session(c360_session: str | None = Cookie(default=None)) -> Session:
    if not c360_session:
        raise HTTPException(401, "Not signed in")
    return unsign(c360_session)


def require(roles: Iterable[Role]) -> Callable[..., Session]:
    allowed = set(roles)

    def dep(session: Session = Depends(current_session)) -> Session:
        if session.role not in allowed:
            raise HTTPException(403, detail={"reason": f"Not available for the {session.role} role"})
        return session

    return dep


def stub(name: str):
    """Serve api/fixtures/<name>.json until the module is real (use_fixtures=True)."""
    if get_settings().use_fixtures:
        return fixture(name)
    raise HTTPException(501, f"{name} not implemented yet")


def live_data() -> bool:
    """Real warehouse data when it exists (and fixtures aren't forced); sample fixtures otherwise."""
    s = get_settings()
    return s.warehouse_path.exists() and not s.force_fixtures


def live_or_fixture(name: str, fn, *args):
    """Call the real service when the warehouse exists; fall back to the fixture otherwise."""
    if live_data():
        out = fn(*args)
        if out is None:
            raise HTTPException(404, f"{name}: not found")
        return out
    return fixture(name)
