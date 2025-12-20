# INC-013: page_view Events Failing Validation — Missing 'url' in Payload

**Date:** 2025-12-16  
**Severity:** P2  
**Duration:** 7 min  
**Detected via:** `events_dead_lettered_total{event_type="page_view"}` spiking to 40+ events

## Symptoms
- `events_dead_lettered_total` counter for `page_view` events jumped from 0 to 40+ in 2 minutes
- `events_retry_total` also elevated for `page_view`
- Other event types (`click`, `session_start`, `session_end`) processing normally
- Dead-letter stream contained `failure_reason: "page_view requires 'url' in payload"`

## Root Cause
The load test generator (`generate_events.py`) had a bug: the `random_event()` function only included `"url"` in the payload for `page_view` events 80% of the time (a randomization error in an earlier version). The remaining 20% of `page_view` events had `{"referrer": "google.com"}` but no `url` key, causing them to fail the `_validate()` check in `consumer.py`.

## Resolution
1. Fixed `generate_events.py` to always include `url` for `page_view` events
2. Verified the validation logic is correct — `page_view` without `url` should indeed be rejected
3. Cleaned up dead-letter queue: `XTRIM events:dead MAXLEN 0`

## Prevention
- Added test `test_validate_rejects_page_view_without_url` to catch this at the validation layer
- Load test generator now has its own unit tests verifying event shape

## Metrics Impact
- **MTTD:** 3 min (dead-letter counter spike on dashboard)
- **MTTR:** 4 min (traced via DLQ `failure_reason` field → load test code fix)
