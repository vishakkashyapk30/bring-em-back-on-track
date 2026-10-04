# ruff: noqa: E501
"""Call recordings (the optional voice pack): play a call, see the line's call-level measures, and draft the post-call
notes from the audio (speech to text, then the same rules as for transcripts). Only the agent who owns the case may open
a recording (api/access.py), and only call-level measures are returned: never pitch, energy, speaking rate, filler rate
or accent (features/voice.py)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from api import access
from api.deps import live_data, require
from common.types import Role
from governance import audit

router = APIRouter(tags=["voice"])
VIEWERS = {Role.agent, Role.hardship_specialist}
_model: dict = {}


def _row(contact_id: str) -> dict:
    from common.db import warehouse

    con = warehouse()
    try:
        con.execute("SET search_path='silver,gold'")
        cols = ["voice_sample_id", "transcript_id", "contact_id", "file_path", "duration_sec", "dead_air_sec",
                "hold_music_sec", "snr_db", "packet_loss_pct", "clipping_pct", "channels", "sample_rate_hz"]
        r = con.execute(f"SELECT {', '.join(cols)} FROM voice_samples WHERE contact_id = ? LIMIT 1", [contact_id]).fetchone()
    finally:
        con.close()
    if not r:
        raise HTTPException(404, "No recording for this call")
    return dict(zip(cols, r, strict=True))


@router.get("/voice/{contact_id}")
def measures(contact_id: str, s=Depends(require(VIEWERS))) -> dict:
    """Does this call have a recording, and what are the line's call-level measures."""
    if not live_data():
        return {"available": False}
    access.contact(s, contact_id)
    try:
        r = _row(contact_id)
    except HTTPException:
        return {"available": False}
    return {"available": True, "contact_id": contact_id, "voice_sample_id": r["voice_sample_id"],
            "audio_url": f"/api/voice/{contact_id}/audio", "stereo": r["channels"] == 2,
            "measures": {k: r[k] for k in ("duration_sec", "dead_air_sec", "hold_music_sec", "snr_db", "packet_loss_pct",
                                           "clipping_pct")},
            "note": "Call-level measures of the line only. Pitch, speaking rate and accent are never read."}


@router.get("/voice/{contact_id}/audio")
def audio(contact_id: str, s=Depends(require(VIEWERS))):
    access.contact(s, contact_id)
    from features.voice import voice_dir

    p = voice_dir() / f"{_row(contact_id)['voice_sample_id']}.wav"
    if not p.exists():
        raise HTTPException(404, "The recording file is not on this machine (optional voice pack)")
    audit.record(s.user_id, s.role, "recording_played", "contact", contact_id, {"voice_sample_id": p.stem})
    return FileResponse(p, media_type="audio/wav")


@router.post("/voice/{contact_id}/draft")
def draft(contact_id: str, s=Depends(require({Role.agent}))) -> dict:
    """Speech to text from the recording, then the same post-call draft as for a transcript. Nothing is saved."""
    access.contact(s, contact_id)
    from decisioning.post_call import draft_from_turns
    from features.voice import audio_to_turns, for_rules, load_model, voice_dir

    try:
        import faster_whisper  # noqa: F401
    except ImportError as e:  # the optional `voice` extra is not installed (for example in the slim Docker image)
        raise HTTPException(503, "Speech to text is not installed on this server (uv sync --extra voice)") from e

    p = voice_dir() / f"{_row(contact_id)['voice_sample_id']}.wav"
    if not p.exists():
        raise HTTPException(404, "The recording file is not on this machine (optional voice pack)")
    if "model" not in _model:
        _model["model"] = load_model("small")[0]
    turns, stereo = audio_to_turns(_model["model"], p)
    d = draft_from_turns(for_rules(turns))
    audit.record(s.user_id, s.role, "voice_draft", "contact", contact_id, {"stereo": stereo, "turns": len(turns)})
    return {"contact_id": contact_id, "stereo": stereo, "source": "speech to text from the recording", "turns": turns,
            "summary": d["summary"], "fields": d["fields"], "checks": d["checks"],
            "note": None if stereo else "Mono recording: the speakers could not be separated, so every line was read by both the customer and the agent rules."}
