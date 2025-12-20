# INC-009: Event Type Validation Bypass — 'Unknown' Events Stored in Postgres

**Date:** 2025-12-14  
**Severity:** P1  
**Duration:** 10 min  
**Detected via:** Postgres query `SELECT DISTINCT event_type FROM events` returned `unknown` alongside valid types

## Symptoms
- Postgres contained rows with `event_type = 'unknown'`
- These events had `status = 'succeeded'` — they passed through the entire pipeline
- No validation errors in worker logs for these events

## Root Cause
The API endpoint (`POST /events`) used a Pydantic `Literal` type to validate `event_type`, correctly rejecting invalid types with 422. However, the worker's `_parse_message()` function defaulted missing `event_type` to `"unknown"` — and the `_validate()` check on `VALID_EVENT_TYPES` didn't include `"unknown"`, so it was rejected. The bug was that an early version of the code used `process_event()` directly (before batch processing was implemented), and that path didn't call `_validate()`.

After batch processing was introduced, the validation path was correct, but legacy events from the early testing phase remained in the database.

## Resolution
1. Verified that the current code path (batch processing) correctly validates event types
2. Cleaned up legacy `unknown` events: `DELETE FROM events WHERE event_type = 'unknown'`
3. Added `CHECK` constraint on `event_type` column (future migration)

## Prevention
- Added `test_validate_rejects_unknown_event_type` test case
- Schema-level validation via Pydantic `Literal` at API layer prevents invalid types from entering the stream

## Metrics Impact
- **MTTD:** N/A (discovered during data audit)
- **MTTR:** 10 min (confirmed current code is correct, cleaned legacy data)
