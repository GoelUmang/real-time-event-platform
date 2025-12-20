# INC-014: Postgres Migration Race Condition on Multi-Worker Startup

**Date:** 2025-12-16  
**Severity:** P2  
**Duration:** 6 min  
**Detected via:** Workers logging `relation "events" does not exist` errors

## Symptoms
- On fresh deployment (`make up`), 2 of 3 workers crashed within the first 5 seconds
- Logs showed: `asyncpg.exceptions.UndefinedTableError: relation "events" does not exist`
- API container started and ran migrations successfully
- Workers that crashed were auto-restarted by Docker and recovered

## Root Cause
The `CREATE TABLE IF NOT EXISTS` migration runs in the API container's lifespan handler. Workers start concurrently with the API and attempt to INSERT before the migration completes. The `depends_on: api: condition: service_healthy` constraint was missing for workers — they only depended on Postgres and Redis being healthy.

Since the API health check (`/docs` endpoint) passes before migrations finish (FastAPI serves docs before lifespan completes in some uvicorn configurations), workers could start too early.

## Resolution
1. Workers don't depend on API — this is by design (workers should be independently deployable)
2. Added `run_migrations(pool)` call to worker startup in `workers/main.py` — migrations are idempotent (`IF NOT EXISTS`)
3. Both API and workers now independently ensure the schema exists

## Prevention
- Idempotent migrations (`CREATE TABLE IF NOT EXISTS`, `DO $$ ... IF NOT EXISTS ...`) are safe to run concurrently
- Added startup log: `logger.info("migrations_complete")` to confirm schema readiness

## Metrics Impact
- **MTTD:** 1 min (worker crash in `docker compose ps`)
- **MTTR:** 5 min (added migration call to worker startup)
