# INC-016: GET /events Returns 500 — JSON Serialization Error for JSONB Payload

**Date:** 2025-12-18  
**Severity:** P2  
**Duration:** 8 min  
**Detected via:** API logs showed `TypeError: Object of type UUID is not JSON serializable`

## Symptoms
- `GET /events/{event_id}` returned HTTP 500 for events that were confirmed in Postgres
- POST endpoint continued to work normally
- Error traceback pointed to Pydantic response serialisation

## Root Cause
The `get_event()` function in `models.py` returned the raw `asyncpg.Record` dict. The `event_id` field was returned as a Python `UUID` object, but the `EventResponse` Pydantic model expected `event_id: str`. When FastAPI tried to serialize the response, it encountered the `UUID` object and threw a `TypeError`.

Additionally, the `payload` field was stored as JSONB in Postgres but returned as a string by `asyncpg` in some configurations, requiring explicit `json.loads()`.

## Resolution
1. Added explicit `str()` conversion for `event_id` in the route handler: `EventResponse(**{**event, "event_id": str(event["event_id"])})`
2. Added JSONB string detection in `get_event()`: if `payload` is a string, parse it with `json.loads()`

## Prevention
- Added test `test_get_event_returns_dict_when_found` verifying JSON payload parsing
- Added test `test_get_event_returns_correct_status` verifying response shape

## Metrics Impact
- **MTTD:** 2 min (500 errors in API logs)
- **MTTR:** 6 min (traced via traceback + added str() conversion)
