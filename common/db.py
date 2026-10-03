"""Database connections.

- DuckDB `warehouse.duckdb`: gold tables, online features, role views. The API and NL-to-SQL open it
  READ-ONLY (D5); only the pipeline writes to it.
- SQLite `ops.db` (WAL): operational writes such as approvals, audit log and hardship events (D8).
"""

from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

import duckdb

from common.config import get_settings

OPS_SCHEMA = Path(__file__).with_name("ops_schema.sql")


def warehouse(read_only: bool = True) -> duckdb.DuckDBPyConnection:
    s = get_settings()
    if read_only and not s.warehouse_path.exists():
        raise FileNotFoundError(f"{s.warehouse_path} not built yet; run `make gold`")
    return duckdb.connect(str(s.warehouse_path), read_only=read_only)


def init_ops_db(path: Path | None = None, attempts: int = 20) -> None:
    """Idempotent. Several uvicorn workers may run this at once; switching to WAL needs a brief exclusive
    lock that `timeout` doesn't always cover, so retry on 'database is locked'."""
    path = path or get_settings().ops_db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    for i in range(attempts):
        try:
            con = sqlite3.connect(path, timeout=10)
            try:
                if con.execute("PRAGMA journal_mode").fetchone()[0].lower() != "wal":
                    con.execute("PRAGMA journal_mode=WAL")
                con.executescript(OPS_SCHEMA.read_text())
                con.commit()
            finally:
                con.close()
            return
        except sqlite3.OperationalError as e:
            if "locked" not in str(e) or i == attempts - 1:
                raise
            time.sleep(0.1 * (i + 1))


@contextmanager
def ops(path: Path | None = None):
    path = path or get_settings().ops_db_path
    if not path.exists():
        init_ops_db(path)
    con = sqlite3.connect(path, timeout=10)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()
