# Quickstart on the sample (no 13 GB download)

The repository carries a small synthetic sample of the Maple Bank release in `data/sample/` (about 5,560 CRM records, 25 MB
compressed; how it was drawn is in `data/sample/README.md`). The whole pipeline, the promise-break model, the next best
action queue, the search index, the benchmark and the web app run on it. Everything is offline: `LLM_PROVIDER=offline`
(rules only, no keys, no paid service) is the default and is set by the commands below.

## What you need

Python 3.12 and [uv](https://docs.astral.sh/uv/), Node 20 or newer, and `make`. About 1 GB of disk for the Python
environment and the build. No GPU, no API keys, no dataset download.

## Run it locally

```bash
make setup        # uv sync (pipeline, ml, llm extras) + npm install
make demo-data    # bronze, silver, identity, gold, quality report, features, model, scores, NBA queue, search index, benchmark
make api          # terminal 1: FastAPI on http://localhost:8000
make web          # terminal 2: Vite on http://localhost:5173
```

Open http://localhost:5173 and pick one of the five personas on the sign-in screen: agent, hardship specialist, team lead,
analyst, data steward.

`make demo-data` takes about 40 seconds on a laptop once the Python environment exists (16 cores; expect 1 to 2 minutes on
a slower machine). It sets `DATA_SOURCE=sample`, deletes only the previous sample warehouse, and writes everything under
`data/sample_build/` (warehouse, bronze Parquet, features, model artefacts, reports, `ops.db`, the search index). It never
touches `data/warehouse.duckdb`, `reports/`, `docs/data_quality_report.md` or `deliverables/` of a full-data build.

| Step | Make target | About |
|---|---|---:|
| Bronze landing (CSV and Parquet to Parquet) | `make bronze` | 4 s |
| Silver (dbt) | `make silver` | 12 s |
| Identity resolution | `make identity` | 1 s |
| Gold (dbt) and the contract tests (11, all pass) | `make gold` | 9 s |
| Data quality report | `make quality` | 1 s |
| Text features, feature store, parity check | `make features` | 7 s |
| Train the promise-break model | `uv run python -m models.ptp_break.train` | 2 s |
| Score open promises, build the NBA queue | `make score` | 2 s |
| Search index over notes and transcripts | `make search-index` | 2 s |
| Benchmark (35 questions, offline) | `make benchmark` | 2 s |

Each step can be run on its own: prefix it with `DATA_SOURCE=sample`, for example `DATA_SOURCE=sample make features`.

### Which data does a command use

`DATA_SOURCE` is `full`, `sample` or `auto` (the default, also when unset):

- `full`: the release in `data/raw/maple_collections_release`, outputs in `data/` (the original flow, unchanged).
- `sample`: `data/sample/maple_collections_sample`, outputs in `data/sample_build/`.
- `auto`: `full` if `data/warehouse.duckdb` exists, else `sample` if a sample warehouse has been built, else `full` if the
  release is on disk, else `sample`. So on a fresh clone `make demo-data && make api` serves the sample, and on a machine
  with a full build the full build wins. Force one with `DATA_SOURCE=sample make api`.

You can also set `RAW_DIR` or `RELEASE_DIR` (any folder with the release's `data/`, `files/`, `schema/`) in `.env`.

## Run it in Docker

```bash
make up-sample                            # same as: DATA_SOURCE=sample docker compose up -d --build
# open http://localhost:8080
```

The `bootstrap` container finds the sample in `data/sample` (mounted from the repository, nothing is downloaded), builds the
warehouse, trains and scores, builds the search index, and exits; then the API and the web container start. The default
`docker compose up` (no `DATA_SOURCE`) still downloads and builds the full release as before.

## What to expect

- Golden C360: about 5,147 customers, about 2,030 with an open case; 11 of 11 contract tests pass.
- Data quality report (`data/sample_build/data_quality_report.md`): 17 issues found, as on the full data, because the sample
  keeps the quirks (duplicate CRM records, mixed date formats, masked phones, lost CIF zeros, mistyped CRM ids).
- Identity: scored matcher precision about 99.9% on deterministic links, about 20 accounts left unlinked and a small steward
  queue (the steward persona has pairs to review).
- NBA queue: about 1,900 open cases; the agent persona (M. Cochran) has about 115 cases and the team lead's batches are there.
- Ask works in rules mode over the sample warehouse and the policy documents. Search finds notes and transcripts.

## Known differences from the full-data results

Metrics are computed on about 0.5 percent of the customers, so counts, rates and model scores differ. Do not compare them with
the numbers in the README, the model card or the deck.

| Area | Full data | Sample |
|---|---|---|
| Volumes (customers, cases, promises) | 1.02 M, 367 k, 239 k | 5,560, 5,873, 6,556 |
| Promise-break model, test AUC, ours / bank v2.1 / blend | 0.71 / 0.69 / 0.77 | about 0.62 / 0.67 / 0.70 (900 head-to-head promises) |
| Base rate of broken promises | the release's | higher (about 0.72 on the test split): the draw over-represents open, hardship and broken-promise customers |
| Benchmark dev questions | the published scores in `docs/benchmark_results.md` | numeric answers mismatch the full-data gold answers by construction (mean about 0.33 on 21 dev questions); policy and refusal questions still score |
| Fairness and aggregates | groups of 10 or more shown | small groups are suppressed more often (`suppression_min_group`) |
| Voice | 2,000 recordings in the optional voice pack | no recordings; the voice panel says there is no recording, speech to text is skipped |
| Operations capacity | sized for the full book | the capacity table is copied whole, so the sample queue is far below capacity |
| Persona data | whatever the full book holds | the draw adds cases from the agent and team lead personas so their screens are not empty |

Two guards apply in sample mode only (`DATA_SOURCE=sample`); the full-data behaviour is not changed:

- `models/ptp_break/dataset.py`: if the fixed date split (train before April 2026, calibration April to June, test July to
  September) leaves a split under 100 promises or with one outcome, the split falls back to 60/20/20 by promise date, and a
  note is printed. On the current sample the date split is large enough, so the note does not appear.
- `models/ptp_break/train.py`: `min_child_samples` is 20 instead of 100, and if fewer than 30 promises carry a bank v2.1 score
  the head-to-head and blend are skipped (the model is saved with decision "use ours") and a note is printed. Also not
  triggered by the current sample, but it protects a re-drawn smaller one.

## Regenerate or resize the sample

Needs the full release in `data/raw/maple_collections_release` (read only):

```bash
make sample                                                     # same draw, byte-identical output
uv run python -m tools.make_sample --customers 2500 --seed 7    # a smaller or different draw
uv run python -m tools.make_sample --stats                      # print the sizes only, write nothing
uv run pytest tests/unit/test_sample.py                         # referential integrity and size budget
```

## Checks

```bash
LLM_PROVIDER=offline uv run pytest tests/unit -q
uv run ruff check .
```

`tests/unit/test_sample.py` checks that every case has an account and (within the release's own rate of mistyped ids) a
customer, every promise's account, case and customer exist, every transcript file named in `call_transcripts` exists, the
history Parquet only holds sampled accounts, the quirks are present, `MANIFEST.csv` is exact, and the size is inside the
budget (150 MB raw, 60 MB compressed).

## Troubleshooting

- `data/sample is missing`: run `git checkout data/sample` (or `make sample` if you have the full release).
- The app shows demo fixtures instead of data: the warehouse is missing; run `make demo-data` and restart `make api`.
- Switch between sample and full: `DATA_SOURCE=full make api` or `DATA_SOURCE=sample make api`.
