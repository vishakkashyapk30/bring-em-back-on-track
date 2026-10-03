"""Export the offline (training) store to Parquet with a definition hash, so a trained model can name exactly
which feature definition it used. Run: python -m features.build_offline"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import duckdb

from common.config import get_settings

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    s = get_settings()
    out = s.features_dir / "offline"
    out.mkdir(parents=True, exist_ok=True)
    definition = (ROOT / "pipeline" / "macros" / "ptp_features.sql").read_text()
    version = hashlib.sha256(definition.encode()).hexdigest()[:12]
    con = duckdb.connect(str(s.warehouse_path), read_only=True)
    con.execute(f"COPY features.f_ptp_offline TO '{out / 'ptp_training.parquet'}' (FORMAT parquet, COMPRESSION zstd)")
    n = con.execute("SELECT count(*) FROM features.f_ptp_offline").fetchone()[0]
    con.close()
    (out / "ptp_training.meta.json").write_text(json.dumps({"rows": n, "definition_sha": version}, indent=2))
    print(f"offline store: {n} rows -> {out / 'ptp_training.parquet'} (definition {version})")


if __name__ == "__main__":
    main()
