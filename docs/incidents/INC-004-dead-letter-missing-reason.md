# INC-004: Dead-Letter Queue Not Draining — Missed Failure Reason

**Date:** 2025-12-12  
**Severity:** P3  
**Duration:** 6 min  
**Detected via:** Manual inspection of `events:dead` stream showed events with empty `failure_reason`

## Symptoms
- `events_dead_lettered_total` counter was incrementing correctly
- But `XRANGE events:dead 0 +` showed events with `failure_reason: ""` (empty string)
- Ops team couldn't triage dead-lettered events without knowing the failure reason

## Root Cause
In `retry_policy.py`, the `handle_failure()` function passed the `reason` parameter to `XADD`, but an early version had a code path where validation errors set `reason=""` instead of a descriptive message. The `_validate()` function in `consumer.py` returned `None` for valid events but an empty string for one edge case (empty `event_type`).

## Resolution
1. Fixed `_validate()` to always return a descriptive error message for failures
2. Added assertion in `handle_failure()` that `reason` is non-empty before dead-lettering
3. Backfilled existing dead-letter entries with correct failure reasons via script

## Prevention
- Added test case `test_dead_letter_contains_failure_reason` verifying the DLQ message content
- Added structlog field `failure_reason` to dead-letter log line for searchability

## Metrics Impact
- **MTTD:** N/A (discovered during routine DLQ inspection)
- **MTTR:** 6 min (code fix + verification)
