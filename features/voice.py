# ruff: noqa: E501
"""Voice in Layer 3: speech to text, then the SAME text features, plus call-level measures only.

What is used from the recordings (the optional 2,000-call voice pack, synthetic text-to-speech):
- **Speech to text** with a local Whisper model (faster-whisper; free, offline). Stereo files carry the agent on the left and
  the customer on the right, so each channel is transcribed on its own and the turns are labelled by speaker; mono files
  are one mixed stream, so they get the speaker label "mixed" and the customer-only rules do not fire on them. The text then
  goes through the same rule extractor as the released transcripts (features/text_rules.py): one definition.
- **Call-level measures** of the line, never of the person: duration, dead air, hold music, noise level, packet loss and
  clipping (from `voice_samples`). Speaker acoustics (pitch, energy, speaking rate, filler rate, accent region) are NEVER
  read: they can stand in for protected traits (V1 section 5, docs/model_card_ptp_break.md). `CALL_LEVEL` is the whole
  allow-list and `assert_call_level` fails if anything else is requested.

Run: `python -m features.voice transcribe --n 300 --model small` (writes data/features/voice_asr.parquet, the turns in
data/features/voice_turns.parquet and
reports/voice_eval.json: word error rate against the released transcript and agreement of the extracted signals).
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

import numpy as np
import pandas as pd

from common.config import get_settings
from features.text_rules import extract

CALL_LEVEL = ("duration_sec", "dead_air_sec", "hold_music_sec", "snr_db", "packet_loss_pct", "clipping_pct", "channels")
FORBIDDEN = ("pitch", "energy", "speaking_rate", "filler", "accent", "pause_count", "voice_id", "customer_voice", "agent_voice")
VOICE_TURN_COLS = ["voice_sample_id", "contact_id", "turn_index", "speaker", "start_sec", "end_sec", "text", "asr_confidence"]
SIGNALS = ("hardship", "dispute", "complaint", "cease_request", "stated_delay_reason", "next_step")


def assert_call_level(cols: list[str]) -> None:
    bad = [c for c in cols if any(f in c.lower() for f in FORBIDDEN)]
    if bad:
        raise ValueError(f"Speaker characteristics are never used from voice: {bad}")


def voice_dir() -> Path:
    return get_settings().raw_dir / "maple_collections_release" / "files" / "voice"


def call_level_measures() -> pd.DataFrame:
    """One row per recording with the allowed call-level measures (the line, not the speaker)."""
    from common.db import warehouse

    assert_call_level(list(CALL_LEVEL))
    con = warehouse()
    try:
        con.execute("SET search_path='silver,gold'")
        return con.execute(
            f"SELECT voice_sample_id, transcript_id, contact_id, {', '.join(CALL_LEVEL)} FROM voice_samples").df()
    finally:
        con.close()


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def wer(ref: str, hyp: str) -> float:
    """Word error rate: edit distance over the reference words."""
    r, h = _words(ref), _words(hyp)
    if not r:
        return 0.0 if not h else 1.0
    d = list(range(len(h) + 1))
    for i, rw in enumerate(r, 1):
        prev, d[0] = d[0], i
        for j, hw in enumerate(h, 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (rw != hw))
    return d[len(h)] / len(r)


def _cuda_libs() -> None:
    """The pip packages nvidia-cublas-cu12 and nvidia-cudnn-cu12 (the `voice` extra) ship the CUDA libraries Whisper needs;
    make them findable before the model loads."""
    import ctypes
    import glob
    import site

    for root in site.getsitepackages():
        for lib in sorted(glob.glob(f"{root}/nvidia/*/lib/*.so*")):
            try:
                ctypes.CDLL(lib, mode=ctypes.RTLD_GLOBAL)
            except OSError:
                pass


def load_model(size: str = "small"):
    """A Whisper model on the GPU when it really works (a one-second test), else on the CPU (slower, works anywhere)."""
    from faster_whisper import WhisperModel

    _cuda_libs()
    try:
        model = WhisperModel(size, device="cuda", compute_type="float16")
        list(model.transcribe(np.zeros(16000, dtype=np.float32), language="en")[0])  # forces the CUDA libraries to load
        return model, "cuda"
    except Exception:  # noqa: BLE001
        return WhisperModel(size, device="cpu", compute_type="int8", cpu_threads=8), "cpu"


def _segments(model, audio: np.ndarray, speaker: str) -> list[dict]:
    segs, _ = model.transcribe(audio, language="en", beam_size=1, vad_filter=True, condition_on_previous_text=False)
    return [{"speaker": speaker, "start_sec": float(s.start), "end_sec": float(s.end), "text": s.text.strip(),
             "asr_confidence": float(np.exp(s.avg_logprob))} for s in segs if s.text.strip()]


def decode_wav(path: Path) -> np.ndarray | tuple[np.ndarray, np.ndarray]:
    """16-bit PCM WAV to float32 at 16 kHz. Stereo comes back as (left=agent, right=customer). Plain numpy: no codec library."""
    import wave

    with wave.open(str(path), "rb") as w:
        rate, ch, raw = w.getframerate(), w.getnchannels(), w.readframes(w.getnframes())
    x = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    chans = [x[i::ch] for i in range(ch)]

    def to16k(a: np.ndarray) -> np.ndarray:
        if rate == 16000:
            return a
        n = int(round(len(a) * 16000 / rate))
        return np.interp(np.linspace(0, len(a) - 1, n), np.arange(len(a)), a).astype(np.float32)

    out = [to16k(c) for c in chans]
    return (out[0], out[1]) if ch == 2 else out[0]


def audio_to_turns(model, path: Path) -> tuple[list[dict], bool]:
    """Speaker-labelled turns from a recording, and whether it was stereo (so speakers are known)."""
    audio = decode_wav(path)
    if isinstance(audio, tuple):
        left, right = audio
        turns = _segments(model, left, "agent") + _segments(model, right, "customer")
        stereo = True
    else:
        turns, stereo = _segments(model, audio, "mixed"), False
    turns.sort(key=lambda t: t["start_sec"])
    for i, t in enumerate(turns, 1):
        t["turn_index"] = i
    return turns, stereo


def for_rules(turns: list[dict]) -> list[dict]:
    """Turns as the text rules should read them. Stereo turns already carry their speaker. A mono recording is one mixed
    stream, so each line is offered to both the customer rules and the agent rules (measured on 100 mono calls: hardship
    95%, dispute 99%, delay reason 92%, next step 91% agreement with the released transcripts, against 68% / 94% / 42% / 29%
    when the mixed lines were ignored by the customer rules)."""
    if all(t["speaker"] in ("agent", "customer") for t in turns):
        return turns
    return [dict(t, speaker="customer") for t in turns] + [dict(t, speaker="agent") for t in turns]


def _source_turns(transcript_id: str, file_path: str) -> list[dict]:
    p = get_settings().raw_dir / "maple_collections_release" / "files" / file_path
    return json.loads(p.read_text())["turns"] if p.exists() else []


def transcribe(n: int = 300, size: str = "small", seed: int = 7) -> dict:
    """Transcribe a stratified sample (stereo and mono, 8 and 16 kHz) and compare with the released transcripts."""
    from common.db import warehouse

    t0 = time.time()
    con = warehouse()
    con.execute("SET search_path='silver,gold'")
    meta = con.execute("""SELECT v.voice_sample_id, v.transcript_id, v.contact_id, v.channels, v.sample_rate_hz, v.duration_sec,
                                 t.file_path AS transcript_path
                          FROM voice_samples v JOIN call_transcripts t USING (transcript_id)""").df()
    con.close()
    parts = [g.sample(min(len(g), max(1, round(n * len(g) / len(meta)))), random_state=seed)
             for _, g in meta.groupby(["channels", "sample_rate_hz"])]
    sample = pd.concat(parts).head(n).reset_index(drop=True)
    model, device = load_model(size)
    rows, turn_rows = [], []
    for r in sample.itertuples():
        path = voice_dir() / f"{r.voice_sample_id}.wav"
        if not path.exists():
            continue
        turns, stereo = audio_to_turns(model, path)
        src = _source_turns(r.transcript_id, r.transcript_path)
        turn_rows += [{"voice_sample_id": r.voice_sample_id, "contact_id": r.contact_id, "turn_index": t["turn_index"],
                       "speaker": t["speaker"], "start_sec": t["start_sec"], "end_sec": t["end_sec"], "text": t["text"],
                       "asr_confidence": t["asr_confidence"]} for t in turns]
        heard, said = " ".join(t["text"] for t in turns), " ".join(t["text"] for t in src)
        from_audio, from_text = extract(for_rules(turns)), extract(src)
        row = {"voice_sample_id": r.voice_sample_id, "transcript_id": r.transcript_id, "contact_id": r.contact_id,
               "stereo": stereo, "sample_rate_hz": int(r.sample_rate_hz), "duration_sec": float(r.duration_sec),
               "wer": wer(said, heard), "asr_confidence": float(np.mean([t["asr_confidence"] for t in turns])) if turns else None,
               "n_turns": len(turns), "text": heard}
        for k in SIGNALS:
            row[f"{k}_audio"], row[f"{k}_text"] = from_audio.get(k), from_text.get(k)
        rows.append(row)
    df = pd.DataFrame(rows)
    out = get_settings().features_dir / "voice_asr.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.drop(columns=["text"]).to_parquet(out, index=False)
    # the speech-to-text itself, kept for search (rag/interactions.py): redaction happens when the index is built
    pd.DataFrame(turn_rows, columns=VOICE_TURN_COLS).to_parquet(get_settings().features_dir / "voice_turns.parquet", index=False)
    report = summarise(df, size, device, round(time.time() - t0))
    rp = get_settings().reports_dir / "voice_eval.json"
    rp.parent.mkdir(parents=True, exist_ok=True)
    rp.write_text(json.dumps(report, indent=2))
    return report


def summarise(df: pd.DataFrame, model: str, device: str, seconds: int) -> dict:
    def agree(sub: pd.DataFrame) -> dict:
        out = {"calls": int(len(sub)), "median_wer": round(float(sub.wer.median()), 3),
               "mean_asr_confidence": round(float(sub.asr_confidence.mean()), 3)}
        for k in ("hardship", "dispute", "complaint", "stated_delay_reason", "next_step"):
            out[f"{k}_agreement"] = round(float((sub[f"{k}_audio"].astype(str) == sub[f"{k}_text"].astype(str)).mean()), 3)
        return out

    return {"model": model, "device": device, "seconds": seconds, "audio_hours": round(float(df.duration_sec.sum()) / 3600, 2),
            "all": agree(df), "stereo": agree(df[df.stereo]) if df.stereo.any() else None,
            "mono": agree(df[~df.stereo]) if (~df.stereo).any() else None,
            "note": ("Agreement = the signal extracted from the recording's text equals the one extracted from the released "
                     "transcript. Mono recordings have no speaker split, so their lines are offered to both the customer and "
                     "the agent rules (for_rules).")}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["transcribe", "call-level"])
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--model", default="small")
    a = ap.parse_args()
    if a.action == "transcribe":
        print(json.dumps(transcribe(a.n, a.model), indent=2))
    else:
        print(call_level_measures().describe().T.to_string())
