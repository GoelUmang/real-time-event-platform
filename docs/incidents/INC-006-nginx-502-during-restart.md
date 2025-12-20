# INC-006: API 502 Errors via nginx When Uvicorn Workers Restart

**Date:** 2025-12-13  
**Severity:** P2  
**Duration:** 5 min  
**Detected via:** Load test reported 502 HTTP errors; nginx error logs showed `upstream connection refused`

## Symptoms
- Load test at 2K e/s showed 15 errors (0.07% error rate) — all HTTP 502
- Errors clustered in a 3-second window
- `events_ingested_total` stopped incrementing for ~2 seconds then resumed

## Root Cause
During a rolling restart of the API container (`docker compose up --build`), nginx continued routing to the old API container while Uvicorn was shutting down. The health check interval (5s) was too slow to detect the restart, resulting in a ~3s window where nginx sent requests to a closing upstream.

## Resolution
1. Added `proxy_next_upstream error timeout http_502` to `nginx.conf` so nginx automatically retries on the next upstream
2. Reduced health check interval from 5s to 2s in `compose.yaml`
3. Set `proxy_read_timeout 10s` (already present) to prevent long hangs

## Prevention
- Documented the rolling restart procedure: scale up new containers first, then remove old
- nginx `least_conn` already distributes across healthy backends

## Metrics Impact
- **MTTD:** 1 min (load test output showed error count)
- **MTTR:** 4 min (nginx config fix + verification with load test)
