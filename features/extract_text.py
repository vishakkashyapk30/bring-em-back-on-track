"""Batch text features (Layer 3, built by rules): run the validated offline extractor over every call transcript
and agent note, and write features.transcript_features and features.note_features into the warehouse.

Each row carries `available_ts` = when the feature could first be known (call end; note last edit, else note time),
so training joins only see text that existed at decision time. Accuracy against the release's 500 public labels
each for transcripts and notes: eval/eval_text_rules.py (transcripts) and docs/feature_store.md.

Run: `python -m features.extract_text` (part of `make features`).
"""

from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ProcessPoolExecutor

import duckdb
import pandas as pd

from common.config import get_settings
from features.text_rules import extract

log = logging.getLogger("extract_text")
FILES = get_settings().raw_dir / "maple_collections_release" / "files"


def _row(fields: dict) -> dict:
    return {"hardship_signal": fields["hardship"], "hardship_reason": fields["hardship_reason"],
            "stated_delay_reason": fields["stated_delay_reason"], "dispute_signal": fields["dispute"],
            "dispute_type": fields["dispute_type"], "complaint_cue": fields["complaint"],
            "cease_request": fields["cease_request"], "next_step": fields["next_step"],
            "ptp_amount_mentioned": (fields["ptp"] or {}).get("amount")}


def _transcript(args: tuple) -> dict:
    tid, contact_id, case_id, end_ts, path = args
    try:
        turns = json.loads((FILES / path).read_text())["turns"]
    except (OSError, KeyError, json.JSONDecodeError):
        return {"transcript_id": tid, "contact_id": contact_id, "case_id": case_id, "available_ts": end_ts,
                "extract_ok": False}
    return {"transcript_id": tid, "contact_id": contact_id, "case_id": case_id, "available_ts": end_ts,
            "extract_ok": True, **_row(extract(turns))}


def _notes(chunk: list[tuple]) -> list[dict]:
    out = []
    for nid, contact_id, case_id, ts, text in chunk:
        out.append({"note_id": nid, "contact_id": contact_id, "case_id": case_id, "available_ts": ts,
                    **_row(extract([{"speaker": "customer", "text": text or ""}]))})
    return out


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    s = get_settings()
    con = duckdb.connect(str(s.warehouse_path))
    con.execute("CREATE SCHEMA IF NOT EXISTS features")
    t0 = time.perf_counter()
    tx = con.sql("""SELECT transcript_id, contact_id, case_id, call_end_ts, file_path
                    FROM silver.call_transcripts""").fetchall()
    with ProcessPoolExecutor() as ex:
        rows = list(ex.map(_transcript, tx, chunksize=500))
    tdf = pd.DataFrame(rows)
    con.register("tdf", tdf)
    con.execute("CREATE OR REPLACE TABLE features.transcript_features AS SELECT * FROM tdf")
    log.info("transcripts: %d rows in %.1fs", len(tdf), time.perf_counter() - t0)

    t1 = time.perf_counter()
    notes = con.sql("""SELECT note_id, contact_id, case_id, coalesce(last_edited_ts, note_ts) AS available_ts, note_text
                       FROM silver.agent_notes""").fetchall()
    chunks = [notes[i:i + 20000] for i in range(0, len(notes), 20000)]
    with ProcessPoolExecutor() as ex:
        nrows = [r for part in ex.map(_notes, chunks) for r in part]
    ndf = pd.DataFrame(nrows)
    con.register("ndf", ndf)
    con.execute("CREATE OR REPLACE TABLE features.note_features AS SELECT * FROM ndf")
    log.info("notes: %d rows in %.1fs", len(ndf), time.perf_counter() - t1)
    for name in ("transcript_features", "note_features"):
        log.info("%s hardship: %s", name, con.sql(
            f"SELECT hardship_signal, count(*) FROM features.{name} GROUP BY 1 ORDER BY 1").fetchall())
    con.close()


if __name__ == "__main__":
    main()
