# INC-017: Dedup Key TTL Mismatch Causing Reprocessed Events After 1 Hour

**Date:** 2025-12-18  
**Severity:** P3  
**Duration:** 6 min  
**Detected via:** Daily audit showed 12 events processed twice (24h apart) with different `processed_at` timestamps

## Symptoms
- 12 events in Postgres had `retry_count=0` and `status=succeeded` but showed up in `events_processed_total` counter twice
- Events were separated by almost exactly 24 hours
- No errors in worker logs — both processing runs appeared successful

## Root Cause
The `dedup:{event_id}` Redis key had a TTL of 86400 seconds (24h). If the same event was somehow re-published to the stream after 24h (e.g., via manual debugging, stream replay, or a retry task that was delayed by a process suspension), the dedup check would pass because the key had expired.

The Postgres `ON CONFLICT DO NOTHING` prevented duplicate rows, but the worker still executed the full processing pipeline (status cache update, counter increment) for the "duplicate" event.

## Resolution
1. Confirmed that Postgres `UNIQUE(event_id) ON CONFLICT DO NOTHING` prevents data corruption
2. The counter inflation was negligible (12 events out of 73K)
3. Documented the dedup TTL trade-off: longer TTL = more memory usage but better dedup coverage

## Prevention
- `ON CONFLICT DO NOTHING` is the hard guarantee — Redis dedup is an optimization
- For production: consider persistent dedup via Postgres `EXISTS` check (slower but durable)

## Metrics Impact
- **MTTD:** N/A (discovered during post-benchmark data audit)
- **MTTR:** 6 min (confirmed no data corruption, documented trade-off)
