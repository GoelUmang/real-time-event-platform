# INC-010: Redis Connection Leak During Burst Traffic

**Date:** 2025-12-14  
**Severity:** P2  
**Duration:** 9 min  
**Detected via:** Redis `INFO clients` showed `connected_clients: 847` (expected ~20)

## Symptoms
- Redis response times increased from sub-1ms to 15-20ms
- `xadd_duration_seconds` p99 spiked from 0.5ms to 50ms
- Worker `XREADGROUP` calls started timing out intermittently
- Redis `maxclients` (default 10,000) not yet hit, but connection churn was high

## Root Cause
Each call to `run_consumer()` created a new `aioredis.from_url()` connection. When a worker crashed and restarted (due to the OOM issue in INC-001), the old connections weren't properly closed. Additionally, `handle_failure()` created background tasks via `asyncio.create_task()` that each referenced the consumer's Redis connection, preventing garbage collection.

## Resolution
1. Refactored Redis connection management to use a module-level singleton (`redis_client.py`) with `get_redis()` / `close_redis()` pattern
2. Worker shutdown handler now explicitly calls `await r.aclose()` in a `finally` block
3. Added Redis connection count to monitoring checklist

## Prevention
- Singleton pattern prevents connection multiplication
- Added `close_redis()` to worker lifespan cleanup
- Documented Redis client lifecycle in design spec

## Metrics Impact
- **MTTD:** 4 min (XADD latency spike visible on dashboard)
- **MTTR:** 5 min (identified via `redis-cli INFO clients`)
