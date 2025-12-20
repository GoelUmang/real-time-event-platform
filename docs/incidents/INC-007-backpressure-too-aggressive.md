# INC-007: Backpressure Threshold Too Aggressive — Workers Stalling at Low Load

**Date:** 2025-12-13  
**Severity:** P3  
**Duration:** 8 min  
**Detected via:** `events_processed_total` rate was 0 even though `events_ingested_total` was incrementing

## Symptoms
- Workers were running but not processing any events
- `redis_consumer_group_lag` showed 0 (no backlog)
- `redis_pending_messages` showed 0
- Worker logs showed repeated `backpressure_check` entries but no `batch_processed`

## Root Cause
Initial `pending_limit` was set to 50 (too low). During normal processing, the pending count briefly exceeded 50 when workers read a batch via `XREADGROUP` but hadn't yet ACKed. This caused the backpressure check to trigger, making the worker sleep 500ms. On wake, the batch had been processed and pending was 0, but the next `XREADGROUP` immediately put messages back into pending, triggering backpressure again — creating a sleep/wake oscillation.

## Resolution
1. Increased `pending_limit` from 50 to 500 in `config.py`
2. Changed `lag_limit` from 100 to 1000
3. Added debug log when backpressure triggers: `logger.debug("backpressure_triggered", lag=lag, pending=pending)`

## Prevention
- Documented backpressure tuning guidelines in `.env.example`
- Threshold should be `pending_limit > worker_batch_size × num_workers × 2`

## Metrics Impact
- **MTTD:** 3 min (noticed zero processing rate on dashboard)
- **MTTR:** 5 min (identified via worker logs showing repeated backpressure triggers)
