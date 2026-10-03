"""Copy the grey-band candidates (identity.review_queue) into ops.db for the steward UI (/steward/identity).
The steward's verdict is written back to ops.db identity_reviews and applied on the next identity run."""

from __future__ import annotations

from common.config import get_settings
from common.db import ops, warehouse


def export_review_queue(limit: int = 5000) -> int:
    con = warehouse(read_only=True)
    rows = con.execute(
        """SELECT pair_id, source_system || ':' || source_ref, candidate_golden_id, score
           FROM identity.review_queue ORDER BY score DESC LIMIT ?""", [limit]).fetchall()
    con.close()
    with ops() as db:
        db.executemany(
            """INSERT OR IGNORE INTO identity_reviews (pair_id, left_id, right_id, match_probability)
               VALUES (?, ?, ?, ?)""", rows)
    return len(rows)


if __name__ == "__main__":
    print(f"exported {export_review_queue()} pairs to {get_settings().ops_db_path}")
