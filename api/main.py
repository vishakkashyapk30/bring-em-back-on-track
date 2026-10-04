"""`make api` -> uvicorn api.main:app --reload. All routes live under /api."""

from __future__ import annotations

import importlib

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import (
    ask,
    assist,
    assistant,
    auth,
    calls,
    customers,
    demo,
    drift,
    features,
    governance,
    hardship,
    nba,
    playbooks,
    public,
    queue,
    radar,
    steward,
    team,
    voice,
)
from common.config import get_settings
from common.db import init_ops_db

# Register offline LLM handlers (import side effects) so complete_json always has a fallback (D13).
OFFLINE_HANDLER_MODULES = ["decisioning.assistant.runner", "decisioning.post_call", "features.text_rules",
                           "governance.drift", "nlq.compose", "nlq.parser", "rag.answer"]
for _m in OFFLINE_HANDLER_MODULES:
    importlib.import_module(_m)

app = FastAPI(title="back-on-track.ai API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ROUTERS = (public, auth, queue, customers, nba, ask, assist, assistant, demo, calls, hardship, radar, team, features,
           governance, steward, playbooks, drift, voice)
for r in ROUTERS:
    app.include_router(r.router, prefix="/api")
app.include_router(importlib.import_module("api.routers.track").router, prefix="/api")  # Track (docs/reference/track_inbox_watchlist.md)
for r in (importlib.import_module(f"api.routers.{m}") for m in ("inbox", "watchlist")):  # docs/reference/track_inbox_watchlist.md
    app.include_router(r.router, prefix="/api")


@app.on_event("startup")
def _startup() -> None:
    init_ops_db()


@app.get("/api/health")
def health() -> dict:
    s = get_settings()
    from common.llm_mode import availability

    return {"ok": True, "fixtures": s.use_fixtures, "llm_provider": s.llm_provider,
            "warehouse": s.warehouse_path.exists(), "llm": availability()}
