"""Supporting service A: post-call summary. Draft from redacted turns with turn citations;
promise checked against promises_to_pay on the contact_id (mismatch highlighted, not fixed); agent approves;
only approved values reach the online store; a hardship cue raises the latch."""

from llm.providers.offline import register


@register("post_call_summary")
def summary_offline(inputs: dict) -> dict:
    """inputs: {turns:[{turn_index, speaker, text}]}. TODO(WS-E): extractive summary + regex promise."""
    return {"summary": {"text": "", "turns": []}, "promise": None,
            "signals": {"hardship_signal": "none", "stated_delay_reason": None, "dispute_signal": False,
                        "complaint_cue": False, "vulnerability_cue": False, "turns": []},
            "next_steps": []}


def draft(contact_id: str) -> dict:
    raise NotImplementedError("TODO(WS-E)")


def approve(contact_id: str, edited: dict, user_id: str) -> int:
    raise NotImplementedError("TODO(WS-E)")
