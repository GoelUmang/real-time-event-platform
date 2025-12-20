# INC-003: Postgres Connection Pool Exhaustion at 1K e/s

**Date:** 2025-12-12  
**Severity:** P1  
**Duration:** 15 min  
**Detected via:** `asyncpg.exceptions.InterfaceError: cannot perform operation: connection pool is closed` in worker logs

## Symptoms
- Workers began logging connection pool errors at sustained 1K e/s
- `events_processed_total` rate dropped to 0 across all workers
- API GET requests also started timing out (shared pool singleton)
- `redis_consumer_group_lag` climbed rapidly

## Root Cause
Default `asyncpg` pool size was `min_size=2, max_size=10`. With 3 workers each using batch upserts inside transactions, the pool was exhausted under sustained load. The pool's `acquire()` blocked indefinitely, causing backlog. Eventually, some connections timed out and the pool entered a degraded state.

## Resolution
1. Increased `db_pool_max_size` from 10 to 20 in `config.py`
2. Added connection pool health logging on startup
3. Restarted workers to reset connection pool state

## Prevention
- Added `db_pool_min_size` and `db_pool_max_size` to `.env.example` with tuning guidance
- Documented connection pool sizing formula: `max_size >= (num_workers × batch_concurrency) + api_connections`
- Dashboard panel added for asyncpg pool utilisation (future: expose as custom metric)

## Metrics Impact
- **MTTD:** 5 min (worker logs emitted JSON errors; lag dashboard alerted)
- **MTTR:** 10 min (identified via `docker compose logs -f worker | grep "pool"`)
