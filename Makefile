# back-on-track.ai tasks. `make help` lists targets.
UV ?= uv
# DATA_SOURCE=sample runs every step on the committed sample (data/sample) and writes under data/sample_build, so it
# never touches a full-data build. `make demo-data` sets it for you. Default (unset) = full data in data/.
ifeq ($(DATA_SOURCE),sample)
OUT_DIR := $(CURDIR)/data/sample_build
REPORTS := data/sample_build/reports
else
OUT_DIR := $(CURDIR)/data
REPORTS := reports
endif
DBT = cd pipeline && C360_DATA_DIR=$(OUT_DIR) C360_WAREHOUSE=$(OUT_DIR)/warehouse.duckdb $(UV) run dbt

.PHONY: help setup setup-rag bronze silver identity gold quality features benchmark train score data api web demo test lint dbt-parse profile types demo-data sample sample-pipeline search-index up-sample

help:
	@grep -E '^[a-z-]+:' Makefile | cut -d: -f1 | tr '\n' ' '; echo

setup:            ## python + web deps
	$(UV) sync --extra pipeline --extra ml --extra llm
	cd web && npm install

setup-rag:        ## heavy: lancedb + fastembed (~400 MB)
	$(UV) sync --extra pipeline --extra ml --extra llm --extra rag

profile:
	$(UV) run python -m scripts.profile.profile_all

quality:          ## regenerate docs/data_quality_report.md from the warehouse
	$(UV) run python -m governance.quality_report

bronze:
	$(UV) run python -m pipeline.ingest

silver:
	$(DBT) run --profiles-dir . --select silver

identity:
	$(UV) run python -m identity.run

gold:
	($(DBT) run --profiles-dir . --select gold) && ($(DBT) test --profiles-dir . --select gold) && mkdir -p $(REPORTS) && cp pipeline/target/run_results.json $(REPORTS)/contract_tests.json

features:          ## text features -> dbt feature models -> offline export -> parity
	$(UV) run python -m features.extract_text && ($(DBT) run --profiles-dir . --select features) && $(UV) run python -m features.build_offline && $(UV) run python -m features.build_online && $(UV) run python -m features.parity

benchmark:        ## answer every benchmark question -> deliverables/benchmark_answers.csv
	$(UV) run python -m eval.run_benchmark

train:
	$(UV) run python -m models.ptp_break.train && $(UV) run python -m models.ptp_break.evaluate

score:            ## score open promises, then build the NBA queue
	$(UV) run python -m models.ptp_break.score && $(UV) run python -m decisioning.nba

search-index:     ## BM25 index over notes and transcripts (data/search.duckdb)
	$(UV) run python -m rag.ingest

data: bronze silver identity gold quality features

dbt-parse:
	$(DBT) parse --profiles-dir .

api:
	$(UV) run uvicorn api.main:app --reload --port 8000

web:
	cd web && npm run dev

types:            ## regenerate web/src/api/openapi.ts from the running API's OpenAPI
	cd web && npx openapi-typescript http://localhost:8000/openapi.json -o src/api/openapi.ts

# ---- run it without the 13 GB dataset: the committed sample in data/sample (about 5,500 CRM records) -------------
sample:           ## regenerate data/sample from the full release in data/raw (maintainers only; deterministic)
	$(UV) run python -m tools.make_sample

demo-data:        ## build the whole system from the sample: about 2 minutes. Then `make api` and `make web`.
	@test -f data/sample/maple_collections_sample/README.md || { echo "data/sample is missing: run 'git checkout data/sample' or 'make sample'"; exit 1; }
	rm -f data/sample_build/warehouse.duckdb data/sample_build/warehouse.duckdb.wal data/sample_build/search.duckdb
	DATA_SOURCE=sample LLM_PROVIDER=offline $(MAKE) --no-print-directory sample-pipeline
	@echo ""
	@echo "Sample build done (data/sample_build). Start the app: 'make api' in one terminal and 'make web' in another,"
	@echo "then open http://localhost:5173. Metrics differ from the full-data results: see docs/quickstart_sample.md"

sample-pipeline: bronze silver identity gold quality features
	$(UV) run python -m models.ptp_break.train
	$(MAKE) --no-print-directory score search-index benchmark

demo:
	@echo "Run 'make api' and 'make web' in two terminals, then open http://localhost:5173"

test:
	$(UV) run pytest
	cd web && npm test --silent

lint:
	$(UV) run ruff check .

# ---- containers ------------------------------------------------------------
.PHONY: up down logs build-images nightly jobs test-containers ps
build-images:
	docker compose build api web
up:               ## the whole system on http://localhost:8080 (bootstrap builds data on first run)
	docker compose up -d --build
up-sample:        ## same, from the committed sample: no download, about 3 minutes on first run
	DATA_SOURCE=sample docker compose up -d --build
down:
	docker compose down
ps:
	docker compose ps
logs:
	docker compose logs -f --tail=100 api web
nightly:          ## full batch: build warehouse -> contract tests -> atomic publish
	docker compose --profile jobs run --rm jobs nightly
jobs:             ## e.g. make jobs TASK=profile
	docker compose --profile jobs run --rm jobs $(TASK)
test-containers:
	docker compose -f compose.yaml -f compose.test.yaml --profile test run --rm --build tests
