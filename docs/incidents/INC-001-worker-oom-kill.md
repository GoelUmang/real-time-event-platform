# INC-001: Worker Container OOM Kill Under Sustained 5K e/s Load

**Date:** 2025-12-11  
**Severity:** P2  
**Duration:** 12 min  
**Detected via:** `events_processed_total` rate dropped to 0; Docker `OOMKilled` in container events  

## Symptoms
- `events_processed_total{status="succeeded"}` rate fell from ~800/s to 0
- `redis_consumer_group_lag` spiked from 0 → 6,200+ within 30 seconds
- Worker container exited with code 137 (OOMKilled)
- API continued to accept events normally (202 responses)

## Root Cause
`asyncio.create_task(delayed_requeue(...))` spawned unbounded in-memory retry tasks during a burst of validation failures (malformed payloads in load test). Each task held event data + a Redis connection reference in memory until the backoff sleep completed. Under sustained 5K e/s with a simulated 10% failure rate, ~500 retry tasks accumulated per second, exhausting the 256 MB container memory limit.

## Resolution
1. Added `pending_limit` backpressure check (consumer pauses when pending > 500) — committed in `backpressure.py`
2. Increased worker container memory limit from 256 MB to 512 MB in `compose.yaml`
3. Restarted affected worker — consumer group rebalanced automatically

## Prevention
- Dashboarded `redis_pending_messages` gauge with alert threshold at 500
- Documented retry task memory footprint in design spec
- Added load test tier specifically targeting high-failure-rate scenarios

## Metrics Impact
- **MTTD:** 2 min (Grafana lag alert fired)
- **MTTR:** 10 min (root cause identified via `docker inspect` + structlog correlation)
