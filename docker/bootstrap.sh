#!/usr/bin/env bash
# One-command start (`docker compose up`): make sure the dataset and the warehouse exist, then exit so the API
# starts. Idempotent: on later runs it finds both and exits in seconds. Force a rebuild with REBUILD=1.
set -euo pipefail
cd /app
RAW=/app/data/raw
REL="$RAW/maple_collections_release"
LIVE="${WAREHOUSE_PATH:-/app/data/warehouse.duckdb}"

if [ ! -f "$REL/README.md" ]; then
  echo "[bootstrap] dataset not found in data/raw: downloading the release from Hugging Face (~2.3 GB)"
  python - <<'PY'
import zipfile
from pathlib import Path
from huggingface_hub import hf_hub_download
raw = Path("/app/data/raw")
zp = hf_hub_download("nuxsh/maple-collections-hackathon", "maple_collections_release.zip",
                     repo_type="dataset", local_dir=raw)
print("[bootstrap] unzipping", zp)
with zipfile.ZipFile(zp) as z:
    z.extractall(raw)
Path(zp).unlink()   # the unzipped folder is all the pipeline needs
PY
else
  echo "[bootstrap] dataset found"
fi

if [ -f "$LIVE" ] && [ "${REBUILD:-0}" != "1" ]; then
  echo "[bootstrap] warehouse found ($LIVE); skipping the pipeline (set REBUILD=1 to rebuild)"
  exit 0
fi

echo "[bootstrap] building the warehouse (bronze, silver, identity, gold + contract tests, features, reports): ~5 min"
exec jobs nightly
