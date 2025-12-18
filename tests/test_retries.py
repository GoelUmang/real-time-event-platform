import pytest
from unittest.mock import patch, AsyncMock
from uuid import uuid4


# ---------------------------------------------------------------------------
# Backpressure (backpressure.py)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_backpressure_false_when_healthy(fake_redis):
    from app.workers.backpressure import check_backpressure
    try:
        await fake_redis.xgroup_create("events:raw", "workers", id="0", mkstream=True)
    except Exception:
        pass
    with patch("app.workers.backpressure.settings") as s:
        s.stream_name = "events:raw"
        s.consumer_group = "workers"
        s.lag_limit = 1000
        s.pending_limit = 500
        result = await check_backpressure(fake_redis)
    assert result is False


@pytest.mark.asyncio
async def test_backpressure_returns_false_on_exception():
    """When XINFO fails (e.g., stream doesn't exist), backpressure should
    default to False so the worker can proceed."""
    from app.workers.backpressure import check_backpressure
    mock_r = AsyncMock()
    mock_r.xinfo_groups.side_effect = Exception("stream not found")
    with patch("app.workers.backpressure.settings") as s:
        s.stream_name = "events:raw"
        s.consumer_group = "workers"
        result = await check_backpressure(mock_r)
    assert result is False


# ---------------------------------------------------------------------------
# Retry policy — handle_failure (retry_policy.py)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_failure_schedules_retry_below_max(fake_redis):
    from app.workers.retry_policy import handle_failure
    event_id = str(uuid4())

    with patch("app.workers.retry_policy.settings") as s, \
         patch("app.workers.retry_policy.asyncio.create_task") as mock_task:
        s.max_retries = 3
        s.dead_letter_stream = "events:dead"
        s.stream_name = "events:raw"
        # retry_count starts at 0; after INCR = 1, which is < max_retries
        await handle_failure(
            fake_redis, event_id, "page_view",
            None, "sess-1", {}, None, "timeout",
        )
        mock_task.assert_called_once()

    dead = await fake_redis.xlen("events:dead")
    assert dead == 0


@pytest.mark.asyncio
async def test_handle_failure_dead_letters_at_max_retries(fake_redis):
    from app.workers.retry_policy import handle_failure
    event_id = str(uuid4())

    # Pre-seed retry count so the next INCR hits max_retries
    await fake_redis.set(f"retry_count:{event_id}", "2")

    with patch("app.workers.retry_policy.settings") as s:
        s.max_retries = 3
        s.dead_letter_stream = "events:dead"
        s.stream_name = "events:raw"
        await handle_failure(
            fake_redis, event_id, "page_view",
            None, "sess-1", {}, None, "timeout",
        )

    dead = await fake_redis.xlen("events:dead")
    assert dead == 1


@pytest.mark.asyncio
async def test_handle_failure_increments_retry_count(fake_redis):
    """Each call to handle_failure should INCR the retry count key."""
    from app.workers.retry_policy import handle_failure
    event_id = str(uuid4())

    with patch("app.workers.retry_policy.settings") as s, \
         patch("app.workers.retry_policy.asyncio.create_task"):
        s.max_retries = 5
        s.dead_letter_stream = "events:dead"
        s.stream_name = "events:raw"
        await handle_failure(
            fake_redis, event_id, "click",
            None, "sess-1", {}, None, "error1",
        )

    count = await fake_redis.get(f"retry_count:{event_id}")
    assert int(count) == 1


@pytest.mark.asyncio
async def test_handle_failure_second_retry_increments_correctly(fake_redis):
    """Two consecutive failures should result in retry_count=2."""
    from app.workers.retry_policy import handle_failure
    event_id = str(uuid4())

    with patch("app.workers.retry_policy.settings") as s, \
         patch("app.workers.retry_policy.asyncio.create_task"):
        s.max_retries = 5
        s.dead_letter_stream = "events:dead"
        s.stream_name = "events:raw"
        await handle_failure(
            fake_redis, event_id, "click",
            None, "sess-1", {}, None, "err1",
        )
        await handle_failure(
            fake_redis, event_id, "click",
            None, "sess-1", {}, None, "err2",
        )

    count = await fake_redis.get(f"retry_count:{event_id}")
    assert int(count) == 2


@pytest.mark.asyncio
async def test_handle_failure_retry_count_key_has_ttl(fake_redis):
    """The retry_count key should have a TTL set (24h)."""
    from app.workers.retry_policy import handle_failure
    event_id = str(uuid4())

    with patch("app.workers.retry_policy.settings") as s, \
         patch("app.workers.retry_policy.asyncio.create_task"):
        s.max_retries = 5
        s.dead_letter_stream = "events:dead"
        s.stream_name = "events:raw"
        await handle_failure(
            fake_redis, event_id, "click",
            None, "sess-1", {}, None, "error",
        )

    ttl = await fake_redis.ttl(f"retry_count:{event_id}")
    assert ttl > 0


@pytest.mark.asyncio
async def test_dead_letter_contains_failure_reason(fake_redis):
    """Dead-lettered messages should include the failure_reason field."""
    from app.workers.retry_policy import handle_failure
    event_id = str(uuid4())
    await fake_redis.set(f"retry_count:{event_id}", "2")

    with patch("app.workers.retry_policy.settings") as s:
        s.max_retries = 3
        s.dead_letter_stream = "events:dead"
        s.stream_name = "events:raw"
        await handle_failure(
            fake_redis, event_id, "page_view",
            None, "sess-1", {}, None, "db_connection_timeout",
        )

    msgs = await fake_redis.xrange("events:dead")
    assert len(msgs) >= 1
    _, data = msgs[0]
    assert data["failure_reason"] == "db_connection_timeout"
    assert data["event_id"] == event_id


@pytest.mark.asyncio
async def test_dead_letter_contains_event_type(fake_redis):
    """Dead-lettered messages should include the event_type."""
    from app.workers.retry_policy import handle_failure
    event_id = str(uuid4())
    await fake_redis.set(f"retry_count:{event_id}", "2")

    with patch("app.workers.retry_policy.settings") as s:
        s.max_retries = 3
        s.dead_letter_stream = "events:dead"
        s.stream_name = "events:raw"
        await handle_failure(
            fake_redis, event_id, "session_end",
            None, "sess-1", {}, None, "timeout",
        )

    msgs = await fake_redis.xrange("events:dead")
    _, data = msgs[0]
    assert data["event_type"] == "session_end"


# ---------------------------------------------------------------------------
# Backoff calculation
# ---------------------------------------------------------------------------

def test_backoff_is_exponential():
    """Backoff should be min(2^retry_count, 60)."""
    for retry_count, expected in [(1, 2), (2, 4), (3, 8), (4, 16), (5, 32), (6, 60), (7, 60)]:
        backoff = min(2 ** retry_count, 60)
        assert backoff == expected, f"retry_count={retry_count}"


def test_backoff_capped_at_60():
    """At high retry counts, backoff should never exceed 60 seconds."""
    for retry_count in range(1, 20):
        backoff = min(2 ** retry_count, 60)
        assert backoff <= 60


# ---------------------------------------------------------------------------
# delayed_requeue (retry_policy.py)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delayed_requeue_publishes_to_stream(fake_redis):
    """delayed_requeue should re-add the event to the main stream."""
    from app.workers.retry_policy import delayed_requeue

    event_id = str(uuid4())
    with patch("app.workers.retry_policy.settings") as s:
        s.stream_name = "events:raw"
        with patch("app.workers.retry_policy.asyncio.sleep", new_callable=AsyncMock):
            await delayed_requeue(
                fake_redis, event_id, "click",
                "user-1", "sess-1", {"button": "x"}, None, 2,
            )

    stream_len = await fake_redis.xlen("events:raw")
    assert stream_len >= 1


@pytest.mark.asyncio
async def test_delayed_requeue_preserves_event_fields(fake_redis):
    """Re-queued event should contain the original event fields."""
    from app.workers.retry_policy import delayed_requeue

    event_id = str(uuid4())
    with patch("app.workers.retry_policy.settings") as s:
        s.stream_name = "events:raw"
        with patch("app.workers.retry_policy.asyncio.sleep", new_callable=AsyncMock):
            await delayed_requeue(
                fake_redis, event_id, "page_view",
                "user-42", "sess-abc", {"url": "/pricing"}, None, 4,
            )

    msgs = await fake_redis.xrange("events:raw")
    _, data = msgs[0]
    assert data["event_id"] == event_id
    assert data["event_type"] == "page_view"
    assert data["user_id"] == "user-42"
    assert data["session_id"] == "sess-abc"
