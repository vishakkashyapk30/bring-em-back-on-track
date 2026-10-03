# Runbook

## Prerequisites

- Linux/macOS, ~20 GB free disk (dataset ~10 GB unzipped + images)
- Docker 24+ with Compose v2 (container path), **or** Python 3.12 via [`uv`](https://docs.astral.sh/uv/) and Node 20 (local path)

## 1. Get the data

```bash
mkdir -p data/raw && cd data/raw
uvx --from 'huggingface_hub[cli]' hf download nuxsh/maple-collections-hackathon \
    maple_collections_release.zip README.md --repo-type dataset --local-dir .
unzip -q maple_collections_release.zip        # -> data/raw/maple_collections_release/
# optional voice pack (2.4 GB): download maple_collections_voice.zip, unzip, copy its files/ into maple_collections_release/
cd ../..
```

Read `data/raw/maple_collections_release/README.md` (conventions: only empty string is null, `NA` is a real code, identifiers as text with leading zeros, Hive-partitioned Parquet). The zip can be deleted after unzipping to save 2.3 GB.

## 2a. Run with Docker (recommended for the demo)

```bash
docker compose up --build   # the whole system on http://localhost:8080
```

That one command builds the images, then a one-off `bootstrap` container downloads the dataset into `./data/raw` if it isn't there, builds the warehouse on the first run (about 5 minutes: ingest, silver, identity, gold + contract tests, features, quality report, benchmark), and exits. The API starts once it succeeds and the web once the API is healthy. Later runs find the data and start in seconds. `REBUILD=1 docker compose up --build` rebuilds the warehouse; `make test-containers` runs the tests in the image; `docker compose down` stops it.



## 2b. Run locally

```bash
cp .env.example .env
make setup               # uv sync + npm install (make setup-rag adds lancedb + fastembed)
make data                # bronze → silver → identity → gold → features
make train && make score
make api                 # terminal 1, :8000
make web                 # terminal 2, http://localhost:5173
make test && make lint
```

## Personas

Sign in at `/login`: agent, hardship specialist, team lead, analyst, data steward. Each sees different screens.

## Troubleshooting

| Symptom | Fix |
|---|---|
| DuckDB out of memory on large tables | Lower `C360_DUCKDB_MEMORY` in `.env`; the Parquet tables are partitioned by year |
| API says `warehouse: false` on `/api/health` | No warehouse published yet: run `make nightly` (or `make data`) |
| `npm` engine warnings | Node 20 is pinned for; jsdom/jest-dom are pinned to Node-20-compatible versions |
| Port 8080 in use | `WEB_PORT=8090 make up` |
| LLM features show "offline" | Expected: offline is the default (D13). Set `LLM_PROVIDER` and keys in `.env` to try a provider |
