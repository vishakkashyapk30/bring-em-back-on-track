#!/usr/bin/env bash
# `jobs <task>`: batch dispatcher for the jobs container.
set -euo pipefail
cd /app

LIVE="${WAREHOUSE_PATH:-/app/data/warehouse.duckdb}"
# Same file name in a separate folder: dbt hard-codes the database name (= file stem) into views, so the
# build file must be called warehouse.duckdb too, or the views break after the swap.
BUILD="/app/data/building/warehouse.duckdb"

dbt_() { (cd pipeline && C360_DATA_DIR=/app/data C360_WAREHOUSE="${C360_WAREHOUSE:-$LIVE}" dbt "$@" --profiles-dir .); }

nightly() {
  # Build into a separate file, test, then atomically publish (DuckDB single-writer rule).
  rm -f "$BUILD" "$BUILD.wal"; mkdir -p "$(dirname "$BUILD")"
  export WAREHOUSE_PATH="$BUILD" C360_WAREHOUSE="$BUILD"
  python -m pipeline.ingest
  dbt_ run --select silver
  python -m identity.run
  dbt_ build --select gold          # contract tests: a failure stops here, nothing is published
  mkdir -p /app/reports && cp pipeline/target/run_results.json /app/reports/contract_tests.json
  python -m features.extract_text
  dbt_ run --select features
  python -m features.build_offline
  python -m features.build_online
  python -m features.parity
  # Layer 4 model steps: optional until the model lands (the bank's v2.1 scores are used meanwhile)
  python -m models.ptp_break.train || echo "ptp model training not available yet; skipping"
  python -m models.ptp_break.evaluate || echo "ptp model evaluation not available yet; skipping"
  python -m governance.quality_report
  python -m eval.run_benchmark
  python -m pipeline.publish "$BUILD" "$LIVE"
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
  fairness)     python -m eval.ptp_test_scores && python -m governance.fairness.report && python -m governance.fairness.nba_rates ;;
  label-sample) shift; python -m eval.label_sample "$@" ;;
  rag-index)    python -m rag.ingest ;;
  shell)        exec bash ;;
  help|*)       echo "usage: jobs {nightly|profile|bronze|identity|dbt <args>|train|benchmark|parity|fairness|label-sample <kind>|rag-index|shell}" ;;
esac
