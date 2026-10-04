# Architecture (build phase)

Deliverable 2 is the final diagram: [`architecture.png`](architecture.png) and [`architecture.pdf`](architecture.pdf) in this folder (also `architecture.svg`). It shows what the build actually runs and is drawn by `make_diagram.py` (`python3 docs/architecture/make_diagram.py`, needs Chrome for the export). The design-phase diagram is `../design/diagrams/architecture_v1.png`. A plain black and white version in the same four-part layout, for comparing the two, is [`architecture_final_v2.png`](architecture_final_v2.png), the final architecture diagram, drawn from the Mermaid source [`architecture_final_v2.mmd`](architecture_final_v2.mmd) with layer 1 laid out horizontally (render with `npx @mermaid-js/mermaid-cli -i architecture_final_v2.mmd -o architecture_final_v2.png -b white -s 3`). The first vertical draft is kept as [`architecture_final.png`](architecture_final.png). This page is the written reference. Design rationale: [`../design_changes.md`](../design_changes.md).

## Logical view: four layers, one use case

```
 SOURCES: five customer-key systems (CRM · Cards · Lending · Core banking CIF · Collections)
          + contacts, promises, notes, transcripts, voice, bureau, ops events, policy documents, 31 tables in all
        │
        ▼
 LAYER 1  Data Product Factory    bronze (raw Parquet) → silver (typed, current, standardised) → gold
          (pipeline/, identity/)  identity: deterministic keys → Splink probability → steward review
                                  gold.c360_customer (+ match confidence) · c360_account · contract tests · quality report
        │
        ├──► LAYER 2  Insight + NLP (semantic/, nlq/, rag/)
        │      question → editable chips → certified metric SQL → guard (read-only role views, sqlglot)
        │      → answer + SQL + sources + caveats, or a refusal · cited policy answers (RAG with precedence)
        │
        ├──► LAYER 3  Feature Store (features/)
        │      registry.yaml = one definition · SQL + text features (+ voice, call-level only)
        │      offline Parquet (point-in-time) and online table from the same SQL · nightly parity check
        │
        └──► LAYER 4  Next Best Action (models/ptp_break/, decisioning/)
               policy gate (rules) → PTP-break risk (LightGBM, vs bank v2.1) → treatment ladder (rules)
               → capacity allocator → plain-English explanation (template, no LLM)
               → HUMAN: agent approves / edits / overrides; team lead approves batches
               supporting services: post-call summary · agent-assist panel · headline capability (H1 or S1)

 GOVERNANCE (governance/, across all layers): role-based access + role DB views · protected-attribute exclusion
            · hardship latch · append-only audit log · monitoring · fairness (proxy + outcome tests)
 AI: offline-first (rules/templates); an optional LLM provider only improves results
```

## Runtime view: containers

```
 browser ──► web (nginx :8080) ──/api/*──► api (FastAPI, all layers in one process)
                                              ├─ read-only ──► warehouse.duckdb · lancedb/ · model artefacts
                                              └─ read/write ─► ops.db (SQLite WAL: approvals, audit, hardship events)
 jobs (run to completion): ingest → dbt silver → identity → dbt gold + contract tests → features → train/evaluate
      → quality report → publish (atomic swap of building/warehouse.duckdb → warehouse.duckdb)
 optional: worker (event re-scoring), ollama (local LLM)
```

## Where a human reviews

NBA actions (one by one; routine digital reminders by batch with a 2% sample first), post-call summaries, identity grey-band pairs, lowering a hardship flag, and offers above the agent's approver level.
