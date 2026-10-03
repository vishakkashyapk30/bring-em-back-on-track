# back-on-track.ai

**back-on-track.ai** for the CIBC Collections Hackathon, by team **Deep in Debt** (Vishak Kashyap K).

*Every customer in one place, every answer in plain English, every next step explained and approved by a person.*

A collections platform on the synthetic Maple Bank dataset, with four layers working end to end:

1. **Data Product Factory:** raw to curated to golden C360, with customer ID matching across the five source systems and a match confidence.
2. **Insight and NLP:** plain-English questions answered over the C360, with the SQL or sources shown and out-of-scope questions refused.
3. **Feature Store:** structured and text features, one definition for training and live scoring.
4. **Next Best Action:** the Layer 4 use case, built in depth. A policy gate, a promise-break model, a treatment ladder and a plain-English explanation, with an agent who approves, edits or overrides every action.

All documentation lives in [`docs/`](docs/README.md). **Judges: start with [`submission.md`](submission.md)**, which links every deliverable and shows where each layer's must-show item is.

## How to run it

**Requirements:** Docker with Compose v2, **or** Python 3.12 ([uv](https://docs.astral.sh/uv/)) and Node 20. About 20 GB of free disk.

**1. Get the data** (optional with Docker, which downloads it for you; about 2.3 GB zipped, 7 GB unzipped):

```bash
mkdir -p data/raw && cd data/raw
uvx --from 'huggingface_hub[cli]' hf download nuxsh/maple-collections-hackathon \
    maple_collections_release.zip --repo-type dataset --local-dir .
unzip -q maple_collections_release.zip && cd ../..
```

**2a. With Docker (recommended):**

```bash
docker compose up --build   # the whole system on http://localhost:8080
```

That one command builds the images, then a one-off `bootstrap` container downloads the dataset into `./data/raw` if it isn't there, builds the warehouse on the first run (about 5 minutes: ingest, silver, identity, gold + contract tests, features, quality report, benchmark), and exits. The API starts once it succeeds and the web once the API is healthy. Later runs find the data and start in seconds. `REBUILD=1 docker compose up --build` rebuilds the warehouse; `make test-containers` runs the tests in the image; `docker compose down` stops it.

**2b. Locally:**

```bash
cp .env.example .env
make setup               # Python + web dependencies
make data               # bronze, silver, identity, gold + contract tests, quality report, features
make benchmark          # answers every benchmark question -> deliverables/benchmark_answers.csv
make api                 # terminal 1: FastAPI on :8000
make web                 # terminal 2: http://localhost:5173
make test && make lint
```

Sign in at `/login` as one of five personas: collections agent, hardship specialist, team lead, strategy analyst or data steward. Each sees different screens. There's more detail and troubleshooting in [`docs/runbook.md`](docs/runbook.md).

## What changed from our design

The full list, with reasons and status, is in [`docs/design_changes.md`](docs/design_changes.md). The main changes:

- **One Layer 4 use case.** Next Best Action is the use case. Post-call summary and agent assist became supporting services inside the NBA screen; the brief asks for one use case.
- **Offline-first AI.** We have no LLM budget, so every AI step has a deterministic fallback (rules and templates), and the system runs fully with `LLM_PROVIDER=offline`. An LLM provider can be plugged in later; it may only improve results, never be required for them.
- **React frontend instead of Streamlit,** themed in CIBC colours, for approve/override flows and role-based screens.
- **Safer by construction:**
  - NL-to-SQL runs on read-only, role-specific database views.
  - Identity matching never lets an LLM decide.
  - Fairness uses both proxy tests and outcome tests.
  - A `possible` hardship flag gets a review deadline.
  - Conflicting policy documents follow a precedence order.
- **Operational writes in SQLite** (approvals, overrides, an append-only audit log), not a nightly-merged side file.
- **Containerised modular monolith:** `web` (nginx), `api` (all layers in one process) and `jobs` (batch). There are no microservices, because nothing at this scale needs one.
- **Atomic warehouse publish:** the nightly build is swapped in only after the contract tests pass.
- **The release's public labels** (500 each for notes and transcripts) replace most hand-labelling. The benchmark uses the release's dev answers and official CSV format.
- **An independent spec test suite,** written by a separate agent that only saw the brief and the design docs.

## AI tools we used, and for what

Details are in [`docs/ai_tools.md`](docs/ai_tools.md).

**To build the project:**
- **Claude Code** (Claude Sonnet 5.5 and Claude Opus 5.5) for planning, scaffolding, code, tests, Docker and documentation. Every change is reviewed by the team member and gated by tests.
- **A separate Claude Code subagent** for the independent spec test suite.
- **The Figma connector**, to read a community landing-page design as visual inspiration.
- **Claude Code plugin skills** (Render, design, dataviz).

**Inside the product:**
- **Offline rules and templates** by default for question parsing, insights, text features and post-call summaries.
- **Local embeddings and LanceDB** for cited policy answers.
- **LightGBM with SHAP** for the promise-break model.
- **Plain code**, deliberately, for the policy gate, treatment ladder, eligibility, simulator, explanations, refusals and the hardship latch.

## Deliverables

| # | Deliverable | Where |
|---|---|---|
| 1 | Code repository and this README | this repo |
| 2 | Architecture diagram | [`docs/architecture/`](docs/architecture/) |
| 3 | Data contract (golden C360, based on DC-COLL-001) | [`docs/contracts/c360_customer.v1.yaml`](docs/contracts/c360_customer.v1.yaml) |
| 4 | Data quality report | [`docs/data_quality_report.md`](docs/data_quality_report.md) |
| 5 | Benchmark answers | `deliverables/benchmark_answers.csv` |
| 6 | Demo video (5 minutes) | link to be added |
| 7 | Pitch deck (10 slides) | submitted via the form |

Status is tracked in [`docs/submission_checklist.md`](docs/submission_checklist.md).

## Repository layout

| Path | What |
|---|---|
| `common/` | Config, DB connections (DuckDB read-only, SQLite ops), enums, the protected-attribute list |
| `pipeline/` | Layer 1: bronze ingest, dbt project (silver, gold, role views, features, contract tests), atomic publish |
| `identity/` | Layer 1: deterministic links, Splink, steward review, stable golden IDs |
| `semantic/`, `nlq/`, `rag/` | Layer 2: metrics, question to chips to guarded SQL to answer, cited policy answers |
| `features/` | Layer 3: registry, offline and online stores, point-in-time joins, parity, text rules |
| `models/ptp_break/`, `decisioning/` | Layer 4: promise-break model; NBA gate, ladder, allocator, explanation; supporting services |
| `governance/` | Audit log, hardship latch, access control, quality report, monitoring, fairness |
| `llm/` | Provider-agnostic LLM client (offline default), prompts, schemas, redaction |
| `api/` | FastAPI routers, schemas (the API contract), sample-data fixtures |
| `web/` | React + Vite + Tailwind app |
| `docs/` | Brief, design-phase submission, contracts, reports, architecture, runbook |
| `Dockerfile`, `compose.yaml`, `docker/` | Containers |
| `render.yaml` | Optional hosted demo on Render (not deployed) |

## Ground rules we enforce

- No protected attributes in decisions (enforced by constraint tests in the test suite).
- Every decision comes with a plain-English reason.
- A person can review and override anything that affects a customer.
- Signs of financial hardship pause pressure actions until a specialist reviews them.
- Every customer-affecting action is written to an append-only audit log.

All data is synthetic (Maple Bank, snapshot 28 Sep 2026).
