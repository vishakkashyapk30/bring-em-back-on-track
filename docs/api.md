# API contract

The contract is the pydantic models in `api/schemas/`, `nlq/schemas.py` and `decisioning/schemas.py`. The live
OpenAPI spec is at `http://localhost:8000/docs` while `make api` runs. After any schema change, run `make types`
so the frontend gets `web/src/api/openapi.ts`.

The endpoint list is in the live OpenAPI spec, and each router declares its allowed roles with `require(...)`. Rules:
- Every response carries `meta` (`as_of`, `freshness_hours`, `fixture`).
- Every write returns `audit_id`.
- 403 → `{detail: {reason}}` (the UI shows "not available for your role").
- While `USE_FIXTURES=true`, unimplemented endpoints return `api/fixtures/<name>.json`. When you implement one,
  keep the fixture's shape (or update the fixture, schema and frontend together).

Live today (not fixtures): `/auth/*`, `/me`, `/health`, `POST /nba/{case_id}/decision` (audit),
`POST /hardship/{golden_id}/flag` (latch), `POST /ask` refusals, `/features/catalog`, `/governance/audit`,
`/governance/contract`.
