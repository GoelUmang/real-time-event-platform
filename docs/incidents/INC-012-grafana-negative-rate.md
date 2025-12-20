# INC-012: Grafana Dashboard Showing Negative Processing Rate

**Date:** 2025-12-15  
**Severity:** P3  
**Duration:** 4 min  
**Detected via:** Grafana panel for "Events Processed / sec" displayed negative values

## Symptoms
- Processing rate panel showed brief negative dips to -200/s
- API ingestion panel was normal
- Actual event processing confirmed working via Postgres queries

## Root Cause
When a worker container restarted (e.g., due to OOM or rolling update), its Prometheus counters reset to 0. The `rate()` function interpreted the counter drop as a decrease, producing negative values until the next scrape window. This is a well-known Prometheus counter-reset artifact.

## Resolution
1. Changed Grafana queries from `rate()` to `increase()` with `> 0` filter for display panels
2. For accurate rate calculation, switched to `sum(rate(...[1m]))` which handles resets correctly when aggregating across multiple instances
3. Added Prometheus recording rules for commonly-used rate queries

## Prevention
- Documented counter-reset behavior in observability section of design spec
- All dashboard queries now use `sum(rate())` pattern for multi-instance metrics
- Added `max_over_time()` guard for single-instance rate panels

## Metrics Impact
- **MTTD:** 1 min (visual anomaly on dashboard)
- **MTTR:** 3 min (Grafana query fix)
