"""Parity check (Layer 3): recompute a sample of online feature rows through the shared definition and compare
them with what the online store serves. A mismatch means the online table is stale or was built differently.

The online model (features.f_ptp_online) and the training model (features.f_ptp_offline) are compiled from the
same macro, so recomputing with the online as-of time must reproduce the stored values exactly.
Run: python -m features.parity  -> prints a summary and writes reports/feature_parity.json
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

from common.config import get_settings

ROOT = Path(__file__).resolve().parents[1]
COMPILED = ROOT / "pipeline" / "target" / "compiled" / "collections360" / "models" / "features" / "f_ptp_online.sql"


def run(sample_size: int = 1000) -> dict:
    s = get_settings()
    if not COMPILED.exists():
        raise FileNotFoundError("Run `make features` (dbt) first so the compiled definition exists")
    sql = COMPILED.read_text()
    con = duckdb.connect(str(s.warehouse_path), read_only=True)
    con.execute("SET search_path = 'silver,gold,features,identity'")
    ids = [r[0] for r in con.execute(
        f"SELECT ptp_id FROM features.f_ptp_online USING SAMPLE {sample_size} ROWS (reservoir, 7)").fetchall()]
    con.execute("CREATE TEMP TABLE sample_ids AS SELECT unnest(?) AS ptp_id", [ids])
    recomputed = f"SELECT r.* FROM ({sql}) r SEMI JOIN sample_ids USING (ptp_id)"
    cols = [c for c in con.sql("SELECT * FROM features.f_ptp_online LIMIT 0").columns if c != "ptp_id"]
    diff = con.sql(f"""
        SELECT count(*) FROM ({recomputed}) r JOIN features.f_ptp_online o USING (ptp_id)
        WHERE {' OR '.join(f'r."{c}" IS DISTINCT FROM o."{c}"' for c in cols)}""").fetchone()[0]
    con.close()
    out = {"sampled": len(ids), "mismatched_rows": int(diff), "columns_checked": len(cols), "ok": diff == 0}
    (s.reports_dir).mkdir(parents=True, exist_ok=True)
    (s.reports_dir / "feature_parity.json").write_text(json.dumps(out, indent=2))
    return out


if __name__ == "__main__":
    print(run())
