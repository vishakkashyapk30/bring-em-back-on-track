"""Append-only audit log in ops.db. Every customer-affecting write calls `record`."""

from __future__ import annotations

import json
from typing import Any

from common.db import ops
from common.hashing import stable_hash


def record(user_id: str, role: str, event_type: str, entity_type: str | None = None,
           entity_id: str | None = None, inputs: Any = None, outputs: Any = None) -> int:
    with ops() as con:
        cur = con.execute(
            """INSERT INTO audit_log (user_id, role, event_type, entity_type, entity_id, input_hash,
               output_hash, payload_json) VALUES (?,?,?,?,?,?,?,?)""",
            (user_id, role, event_type, entity_type, entity_id,
             stable_hash(inputs) if inputs is not None else None,
             stable_hash(outputs) if outputs is not None else None,
             json.dumps({"inputs": inputs, "outputs": outputs}, default=str)),
        )
        return int(cur.lastrowid)


def query(limit: int = 200, **filters) -> list[dict]:
    where = " AND ".join(f"{k} = ?" for k in filters) or "1=1"
    with ops() as con:
        rows = con.execute(f"SELECT * FROM audit_log WHERE {where} ORDER BY audit_id DESC LIMIT ?",
                           (*filters.values(), limit)).fetchall()
    return [dict(r) for r in rows]
