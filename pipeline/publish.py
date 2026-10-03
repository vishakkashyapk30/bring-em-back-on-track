"""Atomic warehouse publish: the nightly job builds into a separate file and, only after the
contract tests pass, replaces the live warehouse. The API opens a new read-only connection per request, so
it picks up the new file without a restart (open handles keep the old inode on Linux).

Usage: python -m pipeline.publish <building.duckdb> <live.duckdb>
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import duckdb


def publish(building: Path, live: Path) -> None:
    if not building.exists():
        raise FileNotFoundError(building)
    con = duckdb.connect(str(building))  # checkpoint so the WAL is folded into the file
    con.execute("CHECKPOINT")
    con.close()
    wal = building.with_suffix(building.suffix + ".wal")
    if wal.exists():
        raise RuntimeError(f"{wal} still exists after CHECKPOINT; refusing to publish a partial warehouse")
    live.parent.mkdir(parents=True, exist_ok=True)
    os.replace(building, live)


if __name__ == "__main__":
    publish(Path(sys.argv[1]), Path(sys.argv[2]))
    print(f"published {sys.argv[1]} -> {sys.argv[2]}")
