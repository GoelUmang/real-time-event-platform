# INC-005: XCLAIM Recovery Loop Processing Same Messages Repeatedly

**Date:** 2025-12-12  
**Severity:** P2  
**Duration:** 10 min  
**Detected via:** `events_processed_total` counter growing faster than `events_ingested_total`

## Symptoms
- Worker logs showed repeated `recovery_claimed` entries for the same message IDs
- `events_processed_total` was 2x higher than `events_ingested_total`
- Postgres showed correct data (ON CONFLICT absorbed duplicates), but metrics were inflated

## Root Cause
The `run_recovery()` function used `XAUTOCLAIM` with `start_id="0-0"` and successfully claimed stale messages. However, when re-processing a claimed message, the `handle_batch()` function ACKed and set the dedup key correctly — but the recovery consumer used a different consumer name (`{id}-recovery`), and the original consumer's PEL entry was already ACKed. The issue was that `XAUTOCLAIM` returned messages that were already successfully processed but hadn't been cleaned from the idle scan window. The recovery function treated them as new.

## Resolution
1. Added dedup check at the start of `handle_batch()` — already present, but the dedup key TTL (24h) was shorter than the XCLAIM idle threshold in one config variant
2. Ensured `_CLAIM_IDLE_MS = 30000` (30s) is always much shorter than `dedup_ttl = 86400` (24h)
3. Added a `recovery_skipped_duplicate` counter to track silent dedup during recovery

## Prevention  
- Added logging for recovery dedup skips
- Added test case for recovery claiming already-processed messages

## Metrics Impact
- **MTTD:** 4 min (ingested vs processed ratio anomaly on dashboard)
- **MTTR:** 6 min (traced via structlog filtering on `recovery_claimed` + `duplicate_skipped`)
