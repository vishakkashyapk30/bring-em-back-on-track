"""Bronze landing: data/raw/* -> data/bronze/<table>.parquet, unchanged + lineage columns.

Run: `make bronze` (python -m pipeline.ingest). Layout of the released dataset is TBC; adjust
`find_source` once the files land (H0).
"""

from __future__ import annotations

import logging
from pathlib import Path

import duckdb

from common.config import get_settings
from pipeline.tables import TABLES

log = logging.getLogger(__name__)


def find_source(raw: Path, table: str, fmt: str) -> list[Path]:
    """Locate the raw file(s) for a table. TODO(WS-A): confirm the real folder/file naming at H0."""
    patterns = {"csv": [f"**/{table}.csv", f"**/{table}*.csv"],
                "parquet": [f"**/{table}/**/*.parquet", f"**/{table}*.parquet"],
                "json": [f"**/{table}*.json", f"**/{table}/**/*.json"]}[fmt]
    for p in patterns:
        hits = sorted(raw.glob(p))
        if hits:
            return hits
    return []


def land_table(con: duckdb.DuckDBPyConnection, table: str, fmt: str, files: list[Path], out: Path) -> int:
    paths = [str(f) for f in files]
    reader = {
        # all_varchar keeps identifiers as text (10-digit CIF has leading zeros); only empty string is null,
        # so the "NA" outcome code and literal "N/A" in notes survive (release README, file conventions).
        "csv": f"read_csv({paths}, all_varchar=true, header=true, filename=true)",
        "parquet": f"read_parquet({paths}, filename=true, union_by_name=true, hive_partitioning=true)",
        "json": f"read_json_auto({paths}, filename=true)",
    }[fmt]
    con.execute(
        f"""COPY (SELECT *, now() AS _loaded_at FROM {reader})
            TO '{out}' (FORMAT parquet, COMPRESSION zstd)"""
    )
    return con.execute(f"SELECT count(*) FROM '{out}'").fetchone()[0]


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    s = get_settings()
    s.bronze_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    for table, fmt in TABLES.items():
        files = find_source(s.raw_dir, table, fmt)
        if not files:
            log.warning("missing source for %s (%s)", table, fmt)
            continue
        n = land_table(con, table, fmt, files, s.bronze_dir / f"{table}.parquet")
        log.info("bronze %-28s %10d rows from %d file(s)", table, n, len(files))
    # TODO(WS-A): flatten call_transcripts turns -> bronze/transcript_turns.parquet


if __name__ == "__main__":
    main()
