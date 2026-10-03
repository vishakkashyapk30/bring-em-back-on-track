"""`make api` -> uvicorn api.main:app --reload. All routes live under /api."""

from __future__ import annotations

import importlib

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import (
    ask,
    assist,
    auth,
    calls,
    customers,
    features,
    governance,
    hardship,
    nba,
    public,
    queue,
    radar,
    steward,
    team,
)
from common.config import get_settings
from common.db import init_ops_db

# Register offline LLM handlers (import side effects) so complete_json always has a fallback (D13).
OFFLINE_HANDLER_MODULES = ["decisioning.post_call", "features.text_rules", "nlq.compose", "nlq.parser", "rag.answer"]
for _m in OFFLINE_HANDLER_MODULES:
    importlib.import_module(_m)

app = FastAPI(title="Collections 360 API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ROUTERS = (public, auth, queue, customers, nba, ask, assist, calls, hardship, radar, team, features, governance,
           steward)
for r in ROUTERS:
    app.include_router(r.router, prefix="/api")


@app.on_event("startup")
def _startup() -> None:
    init_ops_db()


@app.get("/api/health")
def health() -> dict:
    s = get_settings()
    return {"ok": True, "fixtures": s.use_fixtures, "llm_provider": s.llm_provider,
            "warehouse": s.warehouse_path.exists()}
