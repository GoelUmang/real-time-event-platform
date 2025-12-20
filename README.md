# High-Throughput Event Processing Platform

A production-grade real-time event ingestion and processing system built with **FastAPI**, **Redis Streams**, **asyncio workers**, and **PostgreSQL**. Designed to demonstrate high-throughput distributed systems patterns: backpressure, idempotency, retry durability, dead-letter queuing, and full observability.

## Architecture

```
Clients
   │
   ▼
FastAPI (port 8000)
├── POST /events  ──────────────────────────► Redis Stream (events:raw)
│   └── writes to Postgres (pending)                │
│                                                   ▼
└── GET /events/{id}              asyncio Workers (×3, port 8001)
    └── reads from Postgres       ├── XREADGROUP with consumer group
                                  ├── backpressure check (lag + pending)
                                  ├── dedup via Redis (dedup:{event_id})
                                  ├── process → update Postgres (succeeded)
                                  ├── XACK on every path (no stuck messages)
                                  └── retry: exponential backoff → dead-letter

Postgres ──── source of truth (event lifecycle, retry count, failure reason)
Redis ──────── transport layer (stream) + cache (status, dedup) — ephemeral
Prometheus ─── scrapes :8000/metrics (API) + :8001/metrics (each worker)
Grafana ─────── dashboards at localhost:3000
```

## Key Design Decisions

| Pattern | Implementation |
|---|---|
| **Idempotency** | Redis `dedup:{event_id}` (24h TTL) + Postgres `UNIQUE(event_id) ON CONFLICT DO NOTHING` |
| **Retry durability** | Always ACK immediately; schedule retry via `asyncio.create_task(delayed_requeue)` with exponential backoff (min(2^n, 60)s) |
| **Dead-letter queue** | After `MAX_RETRIES=3`, event moved to `events:dead` stream with failure reason |
| **Backpressure** | Workers pause when consumer group lag > 1000 or pending > 500 (checked via `XINFO GROUPS`) |
| **Horizontal scaling** | `docker compose up --scale worker=3`; each worker gets its own consumer name, same group |

## Stack

- **FastAPI** + **uvicorn** — async HTTP ingestion API
- **Redis Streams** — event queue with consumer groups
- **asyncpg** — async PostgreSQL driver
- **structlog** — structured JSON logging
- **Prometheus** + **Grafana** — metrics and dashboards
- **Docker Compose** — one-command deployment

## Quick Start

**Prerequisites**: Docker Desktop running, Python 3.11+

```bash
# Start all 9 containers (postgres, redis, api, 4 workers, prometheus, grafana)
make up

# Verify all containers are healthy
docker compose ps

# Send 4 seed events through the full pipeline
make seed

# Check an event was processed end-to-end
curl http://localhost:8000/events/<event_id_from_seed_output>
# → {"status": "succeeded", "retry_count": 0, ...}

# Check API Prometheus metrics
curl -sL http://localhost:8000/metrics/ | grep events_ingested

# View Grafana dashboards
open http://localhost:3000  # admin / admin
```

To tear everything down (including volumes):
```bash
make down
```

## API

### `POST /events`

Ingests a new event. Returns immediately (202 Accepted) after writing to Postgres and publishing to Redis Stream.

```bash
curl -X POST http://localhost:8000/events \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "page_view",
    "session_id": "sess-abc123",
    "user_id": "user-42",
    "payload": {"path": "/home", "referrer": "google.com"},
    "client_timestamp": "2025-12-15T12:00:00Z"
  }'

# → {"event_id": "550e8400-...", "message": "accepted"}
```

Supported `event_type` values: `page_view`, `click`, `session_start`, `session_end`

### `GET /events/{event_id}`

Retrieves the full event record from Postgres.

```bash
curl http://localhost:8000/events/550e8400-e29b-41d4-a716-446655440000

# → {
#     "event_id": "550e8400-...",
#     "event_type": "page_view",
#     "status": "succeeded",
#     "retry_count": 0,
#     "failure_reason": null,
#     "created_at": "2025-12-15T12:00:00Z",
#     "processed_at": "2025-12-15T12:00:00.071Z"
#   }
```

Status values: `pending` → `processing` → `succeeded` | `failed`

## Observability

### Prometheus Metrics

| Metric | Type | Labels | Description |
|---|---|---|---|
| `events_ingested_total` | Counter | `event_type` | Events received by API |
| `events_processed_total` | Counter | `status` | Events processed by workers |
| `event_processing_duration_seconds` | Histogram | `event_type` | Worker processing latency |
| `events_retry_total` | Counter | — | Retry attempts scheduled |
| `events_dead_lettered_total` | Counter | — | Events moved to dead-letter queue |
| `redis_consumer_group_lag` | Gauge | `group` | Unread messages in stream |
| `redis_pending_messages` | Gauge | `group` | Acknowledged-but-unACKed messages |

Endpoints: `http://localhost:8000/metrics/` (API), `http://localhost:8001/metrics/` (worker, per instance)

### Grafana

Grafana auto-provisions the Prometheus datasource. Access at `http://localhost:3000` (default credentials: `admin` / `admin`).

Suggested panels:
- `rate(events_ingested_total[1m])` — ingestion throughput
- `rate(events_processed_total{status="succeeded"}[1m])` — processing throughput
- `histogram_quantile(0.99, rate(event_processing_duration_seconds_bucket[1m]))` — p99 latency
- `redis_consumer_group_lag` — queue depth

### Logs

All services emit structured JSON logs via structlog:

```bash
make logs  # tail all services
docker compose logs -f api
docker compose logs -f worker
```

## Running Tests

```bash
# Run full suite with coverage
make test

# → 111 tests, all passing
# Coverage: app/ modules
```

Tests use `fakeredis` for Redis isolation and `AsyncMock`/`MagicMock` for asyncpg pool mocking. No external dependencies required.

## Load Testing

```bash
# Run the full benchmark suite (100 → 500 → 1000 → 2000 events/sec)
make bench

# Or run the event generator directly
python load_testing/generate_events.py --rate 500 --duration 30 --url http://localhost:8000
```

Results are captured in [architecture/benchmark-results.md](architecture/benchmark-results.md).

**Measured results** (Apple M4, Docker Desktop, 4 workers, 1 API instance):
- Max ingestion: **~888 events/sec** (API-bound; workers never lagged)
- Processing latency: **p50 < 0.5ms, p95 < 1ms, p99 < 5ms**
- 75,609 events processed across all benchmark stages — **0 errors, 0 retries, 0 dead-lettered**

## Project Structure

```
.
├── app/
│   ├── api/           # FastAPI routes, schemas, main app
│   ├── core/          # Config (pydantic-settings), logging, Prometheus metrics
│   ├── producer/      # event_publisher.py — XADD to Redis Stream
│   ├── storage/       # asyncpg pool, SQL models, Redis client singleton
│   └── workers/       # consumer, processor, backpressure, retry_policy
├── docker/
│   ├── compose.yaml
│   ├── Dockerfile.api
│   ├── Dockerfile.worker
│   ├── prometheus.yml
│   └── grafana/provisioning/datasources/
├── load_testing/      # async httpx event generators, benchmark runner
├── scripts/           # seed_data.py, run_benchmark.sh, reset_env.sh
├── tests/             # pytest suite with conftest.py fixtures
├── architecture/      # benchmark-results.md template
├── docs/incidents/    # 15+ production-style incident reports
└── Makefile
```

## Event Lifecycle

```
POST /events
    │
    ├── INSERT into postgres (status=pending)
    ├── XADD to events:raw stream
    └── return 202

Worker picks up via XREADGROUP
    │
    ├── check Redis dedup key → skip if duplicate
    ├── set dedup:{event_id} (24h TTL)
    ├── UPDATE status=processing
    ├── validate + process event
    ├── UPDATE status=succeeded, set processed_at
    ├── SET status cache in Redis (1h TTL)
    └── XACK

On failure:
    ├── XACK immediately (never leave un-ACKed)
    ├── increment retry_count in Postgres
    ├── if retry_count < 3: schedule delayed_requeue (backoff 2^n seconds)
    └── if retry_count >= 3: XADD to events:dead, UPDATE status=failed
```
