# INC-008: Prometheus Scrape Failures — Worker Metrics Port Conflict

**Date:** 2025-12-14  
**Severity:** P3  
**Duration:** 7 min  
**Detected via:** Grafana dashboard panels for worker metrics showed "No data"

## Symptoms
- API metrics panels (ingestion rate, XADD latency) worked correctly
- Worker metrics panels (processing rate, lag, pending) showed "No data"
- Prometheus targets page showed `worker:8001` as `DOWN`

## Root Cause
When scaling workers to 3 replicas (`--scale worker=3`), all 3 containers exposed port 8001 internally. However, the Prometheus `static_configs` had only one target: `worker:8001`. Docker Compose DNS round-robins across replicas, but Prometheus only scraped one instance at a time and the metrics from all 3 workers were not aggregated correctly. When the DNS resolved to a different worker between scrapes, the counters appeared to reset.

## Resolution
1. Updated `prometheus.yml` to use Docker service discovery pattern
2. Workers now use the `HOSTNAME` environment variable as a label, making each worker distinguishable in Prometheus
3. Grafana queries updated to `sum(rate(...)) by (status)` to aggregate across all worker instances

## Prevention
- Documented multi-replica Prometheus scraping in design spec
- Added `instance` label verification to post-deployment checklist

## Metrics Impact
- **MTTD:** 5 min (noticed "No data" on Grafana during load test review)
- **MTTR:** 2 min (prometheus.yml config fix)
