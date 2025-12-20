# INC-002: Duplicate Events in Postgres After Redis Restart

**Date:** 2025-12-11  
**Severity:** P2  
**Duration:** 8 min  
**Detected via:** `events_processed_total` double-counted; manual DB query showed duplicate `event_id` rows

## Symptoms
- After Redis restart during maintenance, `events_processed_total{status="succeeded"}` spiked briefly
- Manual `SELECT count(*), event_id FROM events GROUP BY event_id HAVING count(*) > 1` returned 0 rows (Postgres constraint held)
- But `events_processed_total` counter was incremented twice for some events, inflating throughput metrics

## Root Cause
When Redis restarted, all `dedup:{event_id}` keys were evicted. Workers re-processed events from the stream's pending entry list (PEL) since those messages hadn't been ACKed before the restart. The Postgres `UNIQUE(event_id) ON CONFLICT DO NOTHING` constraint correctly prevented duplicate rows, but the Prometheus counter `events_processed.labels(status="succeeded").inc()` was called before the INSERT — so the counter was inflated even when the insert was a no-op.

## Resolution
1. Moved the counter increment to after verifying the batch insert succeeded (post-`batch_upsert_events`)
2. Redis AOF persistence was already enabled; confirmed `appendonly yes` in Redis config

## Prevention
- Counter now only increments after confirmed DB write
- Added integration test verifying dedup after Redis flush

## Metrics Impact
- **MTTD:** 3 min (noticed anomaly in Grafana ingested vs. processed rate mismatch)
- **MTTR:** 5 min (traced via structlog `duplicate_skipped` log absence + Prometheus counter correlation)
