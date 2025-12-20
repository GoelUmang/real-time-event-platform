# INC-011: Consumer Group Not Created — Workers Blocked on Startup

**Date:** 2025-12-15  
**Severity:** P2  
**Duration:** 5 min  
**Detected via:** Workers running but `events_processed_total` at 0; structlog showed `XREADGROUP` errors

## Symptoms
- All 3 worker containers started successfully (health checks passed)
- No events being processed — `events_processed_total` stayed at 0
- Worker logs showed: `NOGROUP No such key 'events:raw' or consumer group 'workers'`
- API was accepting events normally and `XADD` succeeding

## Root Cause
Workers started before the API had published any events. The `XGROUP CREATE ... MKSTREAM` in `run_consumer()` creates the stream and group if they don't exist. However, the `try/except` block that catches "group already exists" was too broad — it also caught the actual connection error when Redis wasn't ready yet. The workers silently swallowed the connection error and then failed on the subsequent `XREADGROUP` call.

## Resolution
1. Made the `except` block in `run_consumer()` specific: catch `redis.exceptions.ResponseError` for "BUSYGROUP" and re-raise other exceptions
2. Added retry loop with 2s backoff for initial group creation
3. Workers now log the specific exception type on startup

## Prevention
- Added `depends_on: redis: condition: service_healthy` in `compose.yaml` (already present)
- Added test verifying consumer group creation error handling

## Metrics Impact
- **MTTD:** 2 min (zero processing rate on dashboard)
- **MTTR:** 3 min (traced via structlog `NOGROUP` error message)
