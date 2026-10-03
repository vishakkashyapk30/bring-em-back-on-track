# Collections 360 tasks. `make help` lists targets.
UV ?= uv
DBT = cd pipeline && C360_DATA_DIR=$(CURDIR)/data C360_WAREHOUSE=$(CURDIR)/data/warehouse.duckdb $(UV) run dbt

.PHONY: help setup setup-rag bronze silver identity gold features train score data api web demo test lint dbt-parse profile types

help:
	@grep -E '^[a-z-]+:' Makefile | cut -d: -f1 | tr '\n' ' '; echo

setup:            ## python + web deps
	$(UV) sync --extra pipeline --extra ml --extra llm
	cd web && npm install

setup-rag:        ## heavy: lancedb + fastembed (~400 MB)
	$(UV) sync --extra pipeline --extra ml --extra llm --extra rag

profile:
	$(UV) run python -m scripts.profile.profile_all

bronze:
	$(UV) run python -m pipeline.ingest

silver:
	$(DBT) run --profiles-dir . --select silver

identity:
	$(UV) run python -m identity.run

gold:
	$(DBT) run --profiles-dir . --select gold && $(DBT) test --profiles-dir . --select gold

features:
	$(DBT) run --profiles-dir . --select features && $(UV) run python -m features.build_online

train:
	$(UV) run python -m models.ptp_break.train && $(UV) run python -m models.ptp_break.evaluate

score:
	$(UV) run python -c "from decisioning.nba import build_queue; build_queue('today')"

data: bronze silver identity gold features

dbt-parse:
	$(DBT) parse --profiles-dir .

api:
	$(UV) run uvicorn api.main:app --reload --port 8000

web:
	cd web && npm run dev

types:            ## regenerate web/src/api/openapi.ts from the running API's OpenAPI
	cd web && npx openapi-typescript http://localhost:8000/openapi.json -o src/api/openapi.ts

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
up:               ## web on http://localhost:8080
	docker compose up -d --build api web
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
