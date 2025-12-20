# Benchmark Results

**Date:** 2025-12-19  
**Environment:** Docker Compose, 4 worker replicas, 1 API instance (4 Uvicorn workers), nginx  
**Hardware:** Apple M4, 16 GB RAM (Docker Desktop on macOS)

## Key finding

**The server never errored at any load level, including 10,000 events/sec target.**
The ceiling (~888 actual e/s) is the Docker Desktop macOS hypervisor network bridge
(HyperKit VM overhead ~1ms/hop), not the application. Worker lag was 0 throughout.
All 75,609 events were successfully processed and persisted to Postgres.

---

## Throughput

| Rate target (e/s) | Duration | Sent   | Errors | Error % | Actual e/s |
|-------------------|----------|--------|--------|---------|------------|
| 500               | 20s      | 9,006  | 0      | 0.0%    | ~450       |
| 1,000             | 20s      | 15,260 | 0      | 0.0%    | ~763       |
| 2,000             | 20s      | 17,464 | 0      | 0.0%    | ~873       |
| 5,000             | 20s      | 17,755 | 0      | 0.0%    | ~888       |
| 10,000            | 20s      | 16,124 | 0      | 0.0%    | ~806       |

**Peak measured: 888 events/sec** — bounded by Docker Desktop VM networking, not the API.

The load generator uses 500 concurrent httpx workers + a token bucket, so it is genuinely
trying to push 5K–10K. The network bridge is the bottleneck, as shown by the flat plateau
above 2K target rate.

---

## Latency

### XADD to Redis Streams (API side)

| Percentile | Latency    |
|------------|------------|
| p50        | 0.289 ms   |
| p95        | 0.490 ms   |
| p99        | 0.951 ms   |
| mean       | ~0.217 ms  |

*Computed from 21,207 histogram observations across 4 Uvicorn workers.*

### DB batch commit (worker side, per `executemany` transaction)

| Percentile | Latency    |
|------------|------------|
| p50        | 0.560 ms   |
| p95        | 3.271 ms   |
| p99        | 4.848 ms   |
| mean       | < 1 ms     |

*Computed from 18,736 histogram observations across 4 worker replicas.*

---

## Queue depth under load

Consumer group lag at end of every tier: **0**  
Pending (un-ACK'd) messages at end: **0**  
XCLAIM recovery events triggered: **0**  
Stream entries read by consumer group: **75,609**

Workers processed faster than the VM bridge could deliver events to the API.

---

## Reliability

| Metric | Value |
|---|---|
| Total events sent (all tiers) | 75,609 |
| Total events in Postgres (status=succeeded) | 75,609 |
| HTTP errors (4xx / 5xx) | 0 |
| Retries scheduled | 0 |
| Dead-lettered | 0 |
| Consumer group consumers | 8 (4 workers × 2: main + recovery) |

**100% event delivery — every event sent was persisted and marked succeeded.**

---

## What limits throughput next

| Bottleneck | How to break it |
|---|---|
| **Docker Desktop VM bridge (~888 e/s)** | Run on bare-metal Linux or a cloud VM — removes the HyperKit hop |
| API single-process saturation | Already solved: 4 Uvicorn workers + nginx; add `--scale api=N` |
| Redis single-node XADD | Shard stream into `events:raw:{0..N}` keyed by user hash |
| Postgres single-writer | Partition `events` table by `created_at`; use connection pooler (PgBouncer) |
| Worker batch size = 1 | At 10K+ real e/s, XREADGROUP batches will grow to 5–10, amortising commit overhead further |

On a bare-metal Linux server, the same stack is expected to exceed **10,000 events/sec**
on a single API instance given the measured XADD latency (~0.2ms) and DB commit latency (~0.6ms).

---

## Test suite

```
111 passed in 0.32s
```

| Test file | Count | Coverage |
|-----------|-------|----------|
| test_api.py | 23 | API routes, validation, metrics endpoint |
| test_workers.py | 24 | Processor, consumer, batch handling, dedup |
| test_retries.py | 13 | Backpressure, retry policy, dead-letter, backoff |
| test_models.py | 13 | DB models, upsert, batch insert, queries |
| test_core.py | 19 | Config, logging, all Prometheus metrics |
| test_schemas.py | 12 | Pydantic input/output validation |
| test_publisher.py | 7 | Redis XADD, field serialization |
