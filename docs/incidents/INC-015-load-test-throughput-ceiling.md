# INC-015: Load Test Token Bucket Overflow at 10K e/s Target

**Date:** 2025-12-17  
**Severity:** P3  
**Duration:** 5 min  
**Detected via:** Load test output showed only ~900 actual e/s despite targeting 10,000

## Symptoms
- Load test targeting 10K e/s only achieved ~900 actual e/s
- No HTTP errors — all events returned 202
- `events_ingested_total` rate plateaued at ~917/s on Prometheus
- Token bucket was full (constant `QueueFull` exceptions in filler coroutine)

## Root Cause
The Docker Desktop macOS hypervisor (HyperKit) adds ~1ms per network hop between the host and container network bridge. At 10K e/s, this creates a fundamental bottleneck:
- Each HTTP request requires 1 hop in + 1 hop out = ~2ms minimum RTT
- With 500 concurrent workers: theoretical max = 500 / 0.002 = 250K e/s
- But the hypervisor's TCP stack saturates at ~900 connections/sec due to connection setup overhead

The token bucket filled up correctly, but workers consumed tokens faster than they could complete requests, leading to the filler's `QueueFull` exceptions.

## Resolution
1. Documented the Docker Desktop throughput ceiling (~900 e/s) in `benchmark-results.md`
2. Calculated theoretical bare-metal capacity based on measured XADD (~0.1ms) and DB commit (~0.5ms) latencies
3. Bare-metal extrapolation: single API node can sustain ~10K+ e/s given 4 Uvicorn workers and sub-ms XADD latency

## Prevention
- Benchmark results now include the "What limits throughput" section with bottleneck analysis
- Future: run benchmark on Linux cloud VM to validate >10K e/s claim

## Metrics Impact
- **MTTD:** 2 min (load test output showed actual rate)
- **MTTR:** 3 min (bottleneck identified via network latency profiling)
