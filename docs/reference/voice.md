# Voice: what we use from the recordings, and what we never use

The optional voice pack has 2,000 synthetic call recordings (text-to-speech, English, 47.4 hours; 70% stereo with the agent on
the left and the customer on the right, 30% one mixed track; 8 kHz and 16 kHz). We use it in three ways, all offline and
free, and we never use anything about how a person sounds.

## What is used

| Use | How | Where |
|---|---|---|
| **Speech to text** | A local Whisper model (faster-whisper, "small") on the GPU, about 100 times faster than real time. Stereo files are transcribed channel by channel, so every turn has a speaker. Mono files are one stream. | `features/voice.py` |
| **The same text features** | The text goes through the same rule extractor as the released transcripts, so there is one definition of hardship, dispute, complaint and next step. A mono line is offered to both the customer rules and the agent rules. | `features/text_rules.py`, `features.voice.for_rules` |
| **Call-level measures of the line** | Duration, dead air, hold music, signal-to-noise, packet loss and clipping, from `voice_samples`. These describe the call, not the speaker. | `features.voice.CALL_LEVEL` |
| **In the app** | On a call's summary page: play the recording, see the line measures, and draft the notes from the audio (nothing is saved until the agent approves). Only the agent who owns the case can play or draft; every play and draft is audited. | `api/routers/voice.py`, `web/src/components/RecordingCard.tsx` |

## What is never used

Pitch, energy, speaking rate, filler rate, pause count, accent region and the voice identifiers. They can stand in for protected
traits (gender, age, accent and so on), and the brief says no protected attributes in decisions. `features.voice.assert_call_level`
fails if any of them is requested, and a unit test covers it. No voice feature goes into the promise-break model.

## How well it works

Measured on all 2,000 recordings against the signal read from the released transcript of the same call (`reports/voice_eval.json`,
`python -m features.voice transcribe --n 2000 --model small`, 32 minutes on an RTX 4060 laptop GPU):

| Signal | Agreement, all | Stereo (1,407) | Mono (593) |
|---|---|---|---|
| Hardship | 92.0% | 92.3% | 91.4% |
| Dispute | 99.1% | 99.0% | 99.3% |
| Complaint | 100% | 100% | 99.8% |
| Next step | 91.1% | 92.0% | 89.2% |
| Stated delay reason | 50.4% | 49.7% | 52.1% |

The median word error rate against the transcript is 0.23 (0.29 on stereo, 0.11 on mono). Part of that is names: the released
transcripts hold the names that were spoken, which a speech model often spells differently, and the rules do not depend on names.
The stated delay reason is the weak one (about half), because the reason words are exactly where the text-to-speech and the
noise (average signal-to-noise 17.7 dB, seven background types) hurt the model most; we report it as it is.

How we chose the mono treatment: with the mixed lines ignored by the customer rules, hardship agreement on 100 mono calls was 68%
and next step 29%. Offering every line to both the customer and agent rules raised them to 95% and 91% on that sample.

## Running it

```bash
uv sync --extra voice                        # faster-whisper and the CUDA libraries (a CPU fallback works, slower)
hf download nuxsh/maple-collections-hackathon maple_collections_voice.zip --repo-type dataset --local-dir data/raw
# unzip it and move maple_collections_voice/files/voice to data/raw/maple_collections_release/files/voice
uv run python -m features.voice transcribe --n 2000 --model small
```

Without the voice pack or the extra, everything else works: the recording card says there is no recording, and drafting from
audio says speech to text is not installed.
