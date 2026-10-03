"""ask(question, role) -> AskResponse. Order: parse -> refuse -> compile -> guard -> preflight -> execute
-> compose -> audit."""

from nlq.schemas import AskResponse


def ask(question: str, role: str, user_id: str) -> AskResponse:
    raise NotImplementedError("TODO(WS-B)")
