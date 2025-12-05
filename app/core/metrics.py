from prometheus_client import Counter, Histogram, Gauge

events_ingested = Counter(
    "events_ingested_total",
    "Total events received by the API",
    ["event_type"],
)

events_processed = Counter(
    "events_processed_total",
    "Total events processed by workers",
    ["status"],
)

processing_duration = Histogram(
    "event_processing_duration_seconds",
    "Time taken to process an event",
    ["event_type"],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0],
)

events_retry_total = Counter(
    "events_retry_total",
    "Total retry attempts",
    ["event_type"],
)

events_dead_lettered = Counter(
    "events_dead_lettered_total",
    "Total events sent to dead-letter queue",
    ["event_type"],
)

consumer_group_lag = Gauge(
    "redis_consumer_group_lag",
    "Consumer group lag",
    ["group"],
)

pending_messages = Gauge(
    "redis_pending_messages",
    "Pending (unacknowledged) messages in consumer group",
    ["group"],
)

batch_size_histogram = Histogram(
    "worker_batch_size",
    "Number of messages processed per XREADGROUP batch",
    buckets=[1, 5, 10, 25, 50, 100, 250, 500],
)

xadd_duration = Histogram(
    "xadd_duration_seconds",
    "Time taken to XADD an event to Redis Streams",
    buckets=[0.0001, 0.0005, 0.001, 0.005, 0.01, 0.05, 0.1],
)

db_batch_commit_duration = Histogram(
    "db_batch_commit_duration_seconds",
    "Time taken to batch-insert a group of events into Postgres",
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
)
