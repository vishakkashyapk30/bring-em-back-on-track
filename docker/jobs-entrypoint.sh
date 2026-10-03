#!/usr/bin/env bash
# `jobs <task>`: batch dispatcher for the jobs container.
set -euo pipefail
cd /app

LIVE="${WAREHOUSE_PATH:-/app/data/warehouse.duckdb}"
BUILD="/app/data/warehouse.building.duckdb"

dbt_() { (cd pipeline && C360_DATA_DIR=/app/data C360_WAREHOUSE="${C360_WAREHOUSE:-$LIVE}" dbt "$@" --profiles-dir .); }

nightly() {
  # Build into a separate file, test, then atomically publish (DuckDB single-writer rule).
  rm -f "$BUILD"
  export WAREHOUSE_PATH="$BUILD" C360_WAREHOUSE="$BUILD"
  python -m pipeline.ingest
  dbt_ run --select silver
  python -m identity.run
  dbt_ build --select gold          # contract tests: a failure stops here, nothing is published
  dbt_ run --select features
  python -m features.build_offline
  python -m features.build_online
  python -m models.ptp_break.train
  python -m models.ptp_break.evaluate
  python -m governance.quality_report
  python -m pipeline.publish "$BUILD" "$LIVE"
  # TODO(WS-B): python -m rag.ingest && rag index build (needs `--extra rag`, already in the image)
}

case "${1:-help}" in
  nightly)      nightly ;;
  profile)      python -m scripts.profile.profile_all ;;
  bronze)       python -m pipeline.ingest ;;
  identity)     python -m identity.run ;;
  dbt)          shift; dbt_ "$@" ;;
  train)        python -m models.ptp_break.train && python -m models.ptp_break.evaluate ;;
  benchmark)    python -m eval.run_benchmark ;;
  parity)       python -c "from features.parity import run; print(run())" ;;
  fairness)     python -c "from governance.fairness import proxy_test, outcome_test; proxy_test.run(); outcome_test.run()" ;;
  label-sample) shift; python -m eval.label_sample "$@" ;;
  rag-index)    python -m rag.ingest ;;
  shell)        exec bash ;;
  help|*)       echo "usage: jobs {nightly|profile|bronze|identity|dbt <args>|train|benchmark|parity|fairness|label-sample <kind>|rag-index|shell}" ;;
esac
