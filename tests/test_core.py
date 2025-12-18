import pytest


# ---------------------------------------------------------------------------
# Settings (config.py)
# ---------------------------------------------------------------------------

def test_settings_has_required_fields():
    from app.core.config import settings
    assert settings.database_url
    assert settings.redis_url
    assert settings.stream_name == "events:raw"
    assert settings.max_retries == 3
    assert settings.consumer_group == "workers"


def test_settings_default_pool_sizes():
    from app.core.config import settings
    assert settings.db_pool_min_size == 2
    assert settings.db_pool_max_size == 20


def test_settings_default_limits():
    from app.core.config import settings
    assert settings.lag_limit == 1000
    assert settings.pending_limit == 500


def test_settings_default_ttls():
    from app.core.config import settings
    assert settings.dedup_ttl == 86400      # 24 hours
    assert settings.status_cache_ttl == 3600  # 1 hour


def test_settings_worker_batch_and_block():
    from app.core.config import settings
    assert settings.worker_batch_size == 10
    assert settings.worker_block_ms == 1000


def test_settings_dead_letter_stream():
    from app.core.config import settings
    assert settings.dead_letter_stream == "events:dead"


# ---------------------------------------------------------------------------
# Structured logging (logging.py)
# ---------------------------------------------------------------------------

def test_configure_logging_returns_bound_logger():
    from app.core.logging import configure_logging, get_logger
    configure_logging("test")
    log = get_logger("test")
    assert log is not None


def test_configure_logging_is_idempotent():
    """Calling configure_logging multiple times should not raise."""
    from app.core.logging import configure_logging, get_logger
    configure_logging("test1")
    configure_logging("test2")
    log = get_logger("test2")
    assert log is not None


def test_get_logger_with_different_names():
    from app.core.logging import get_logger
    log1 = get_logger("api")
    log2 = get_logger("worker")
    assert log1 is not None
    assert log2 is not None


# ---------------------------------------------------------------------------
# Prometheus metrics (metrics.py)
# ---------------------------------------------------------------------------

def test_metrics_are_defined():
    from app.core.metrics import (
        events_ingested, events_processed, processing_duration,
        events_retry_total, events_dead_lettered,
        consumer_group_lag, pending_messages,
        batch_size_histogram, xadd_duration, db_batch_commit_duration,
    )
    events_ingested.labels(event_type="page_view").inc()
    events_processed.labels(status="succeeded").inc()
    batch_size_histogram.observe(10)
    assert True  # no exceptions raised


def test_ingested_counter_labels():
    from app.core.metrics import events_ingested
    for event_type in ["page_view", "click", "session_start", "session_end"]:
        events_ingested.labels(event_type=event_type).inc()


def test_processed_counter_labels():
    from app.core.metrics import events_processed
    for status in ["succeeded", "failed"]:
        events_processed.labels(status=status).inc()


def test_retry_counter_has_event_type_label():
    from app.core.metrics import events_retry_total
    events_retry_total.labels(event_type="page_view").inc()
    events_retry_total.labels(event_type="click").inc()


def test_dead_letter_counter_has_event_type_label():
    from app.core.metrics import events_dead_lettered
    events_dead_lettered.labels(event_type="page_view").inc()


def test_processing_duration_histogram_has_buckets():
    from app.core.metrics import processing_duration
    # Histogram should have event_type label
    processing_duration.labels(event_type="click").observe(0.001)


def test_xadd_duration_histogram():
    from app.core.metrics import xadd_duration
    xadd_duration.observe(0.0001)


def test_db_batch_commit_duration_histogram():
    from app.core.metrics import db_batch_commit_duration
    db_batch_commit_duration.observe(0.005)


def test_consumer_group_lag_gauge():
    from app.core.metrics import consumer_group_lag
    consumer_group_lag.labels(group="workers").set(42)


def test_pending_messages_gauge():
    from app.core.metrics import pending_messages
    pending_messages.labels(group="workers").set(10)
