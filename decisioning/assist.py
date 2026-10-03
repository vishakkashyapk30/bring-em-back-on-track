"""Supporting service B: agent-assist panel: cited policy answers (rag), eligibility, replayed
transcript prompts ('Hardship mentioned: check program eligibility')."""


def policy_answer(question: str, case_id: str | None) -> dict:
    raise NotImplementedError("TODO(WS-B/WS-E)")


def replay_prompts(contact_id: str) -> list[dict]:
    raise NotImplementedError("TODO(WS-E)")
