import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


def make_mock_pool():
    conn = AsyncMock()
    # conn.transaction() must return an async context manager directly (not a
    # coroutine), so override the AsyncMock default with a plain MagicMock.
    tx_cm = MagicMock()
    tx_cm.__aenter__ = AsyncMock(return_value=None)
    tx_cm.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=tx_cm)

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.acquire.return_value = cm
    pool._conn = conn
    return pool


# ---------------------------------------------------------------------------
# process_event (processor.py)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_process_event_inserts_and_succeeds(fake_redis):
    from app.workers.processor import process_event
    event_id = str(uuid4())
    mock_pool = make_mock_pool()

    await process_event(
        mock_pool, fake_redis, event_id,
        "page_view", "user-1", "sess-1", {"url": "/home"}, None,
    )

    # upsert_event_succeeded calls conn.execute once
    mock_pool._conn.execute.assert_called_once()
    assert await fake_redis.get(f"status:{event_id}") == "succeeded"


@pytest.mark.asyncio
async def test_process_event_rejects_unknown_type(fake_redis):
    from app.workers.processor import process_event
    mock_pool = make_mock_pool()

    with pytest.raises(ValueError, match="Unknown event_type"):
        await process_event(
            mock_pool, fake_redis, str(uuid4()),
            "bad_type", None, "sess-1", {}, None,
        )


@pytest.mark.asyncio
async def test_process_event_click_succeeds(fake_redis):
    from app.workers.processor import process_event
    event_id = str(uuid4())
    mock_pool = make_mock_pool()

    await process_event(
        mock_pool, fake_redis, event_id,
        "click", "user-1", "sess-1", {"button": "cta"}, None,
    )
    assert await fake_redis.get(f"status:{event_id}") == "succeeded"


@pytest.mark.asyncio
async def test_process_event_session_start_succeeds(fake_redis):
    from app.workers.processor import process_event
    event_id = str(uuid4())
    mock_pool = make_mock_pool()

    await process_event(
        mock_pool, fake_redis, event_id,
        "session_start", None, "sess-1", {}, None,
    )
    assert await fake_redis.get(f"status:{event_id}") == "succeeded"


@pytest.mark.asyncio
async def test_process_event_session_end_succeeds(fake_redis):
    from app.workers.processor import process_event
    event_id = str(uuid4())
    mock_pool = make_mock_pool()

    await process_event(
        mock_pool, fake_redis, event_id,
        "session_end", None, "sess-1", {}, None,
    )
    assert await fake_redis.get(f"status:{event_id}") == "succeeded"


@pytest.mark.asyncio
async def test_process_event_page_view_without_url_raises(fake_redis):
    """page_view events without 'url' in payload must be rejected."""
    from app.workers.processor import process_event
    mock_pool = make_mock_pool()

    with pytest.raises(ValueError, match="page_view requires 'url'"):
        await process_event(
            mock_pool, fake_redis, str(uuid4()),
            "page_view", None, "sess-1", {"referrer": "google.com"}, None,
        )


@pytest.mark.asyncio
async def test_process_event_with_null_user_id(fake_redis):
    """null user_id should be accepted (anonymous sessions)."""
    from app.workers.processor import process_event
    event_id = str(uuid4())
    mock_pool = make_mock_pool()

    await process_event(
        mock_pool, fake_redis, event_id,
        "click", None, "sess-anon", {"button": "x"}, None,
    )
    assert await fake_redis.get(f"status:{event_id}") == "succeeded"


@pytest.mark.asyncio
async def test_process_event_sets_status_cache(fake_redis):
    """After processing, the status should be cached in Redis."""
    from app.workers.processor import process_event
    event_id = str(uuid4())
    mock_pool = make_mock_pool()

    await process_event(
        mock_pool, fake_redis, event_id,
        "click", "user-1", "sess-1", {"button": "x"}, None,
    )

    # status key should exist in Redis with value 'succeeded'
    cached = await fake_redis.get(f"status:{event_id}")
    assert cached == "succeeded"


# ---------------------------------------------------------------------------
# handle_batch (consumer.py)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_batch_skips_duplicate(fake_redis):
    from app.workers.consumer import handle_batch
    event_id = str(uuid4())
    await fake_redis.set(f"dedup:{event_id}", "1")
    try:
        await fake_redis.xgroup_create("events:raw", "workers", id="0", mkstream=True)
    except Exception:
        pass

    mock_pool = make_mock_pool()
    with patch("app.workers.consumer.models.batch_upsert_events", new_callable=AsyncMock) as mock_upsert:
        await handle_batch(fake_redis, mock_pool, [
            ("msg-1", {
                "event_id": event_id,
                "event_type": "page_view",
                "user_id": "",
                "session_id": "sess-1",
                "payload": '{"url": "/home"}',
                "client_timestamp": "",
            }),
        ])
        mock_upsert.assert_not_called()


@pytest.mark.asyncio
async def test_handle_batch_inserts_new_events(fake_redis):
    from app.workers.consumer import handle_batch
    event_id = str(uuid4())
    try:
        await fake_redis.xgroup_create("events:raw", "workers", id="0", mkstream=True)
    except Exception:
        pass

    mock_pool = make_mock_pool()
    with patch("app.workers.consumer.models.batch_upsert_events", new_callable=AsyncMock) as mock_upsert, \
         patch("app.workers.consumer.settings") as s:
        s.stream_name = "events:raw"
        s.consumer_group = "workers"
        s.dedup_ttl = 86400
        s.status_cache_ttl = 3600
        await handle_batch(fake_redis, mock_pool, [
            ("msg-1", {
                "event_id": event_id,
                "event_type": "page_view",
                "user_id": "user-1",
                "session_id": "sess-1",
                "payload": '{"url": "/home"}',
                "client_timestamp": "",
            }),
        ])
        mock_upsert.assert_called_once()


@pytest.mark.asyncio
async def test_handle_batch_sets_dedup_key_after_success(fake_redis):
    """After successful batch insert, dedup keys should be set."""
    from app.workers.consumer import handle_batch
    event_id = str(uuid4())
    try:
        await fake_redis.xgroup_create("events:raw", "workers", id="0", mkstream=True)
    except Exception:
        pass

    mock_pool = make_mock_pool()
    with patch("app.workers.consumer.models.batch_upsert_events", new_callable=AsyncMock), \
         patch("app.workers.consumer.settings") as s:
        s.stream_name = "events:raw"
        s.consumer_group = "workers"
        s.dedup_ttl = 86400
        s.status_cache_ttl = 3600
        await handle_batch(fake_redis, mock_pool, [
            ("msg-1", {
                "event_id": event_id,
                "event_type": "click",
                "user_id": "",
                "session_id": "sess-1",
                "payload": '{"button": "x"}',
                "client_timestamp": "",
            }),
        ])

    assert await fake_redis.get(f"dedup:{event_id}") == "1"


@pytest.mark.asyncio
async def test_handle_batch_db_failure_skips_ack(fake_redis):
    """When the DB batch insert fails, messages should NOT be ACKed
    so XCLAIM recovery can retry them."""
    from app.workers.consumer import handle_batch
    event_id = str(uuid4())
    try:
        await fake_redis.xgroup_create("events:raw", "workers", id="0", mkstream=True)
    except Exception:
        pass

    mock_pool = make_mock_pool()
    with patch("app.workers.consumer.models.batch_upsert_events",
               new_callable=AsyncMock, side_effect=Exception("DB down")), \
         patch("app.workers.consumer.settings") as s:
        s.stream_name = "events:raw"
        s.consumer_group = "workers"
        s.dedup_ttl = 86400
        s.status_cache_ttl = 3600
        await handle_batch(fake_redis, mock_pool, [
            ("msg-1", {
                "event_id": event_id,
                "event_type": "click",
                "user_id": "",
                "session_id": "sess-1",
                "payload": '{"button": "x"}',
                "client_timestamp": "",
            }),
        ])

    # Dedup key should NOT be set since DB insert failed
    assert await fake_redis.get(f"dedup:{event_id}") is None


@pytest.mark.asyncio
async def test_handle_batch_validation_failure_triggers_dead_letter(fake_redis):
    """Events with unknown event_type should be dead-lettered via handle_failure."""
    from app.workers.consumer import handle_batch
    event_id = str(uuid4())
    try:
        await fake_redis.xgroup_create("events:raw", "workers", id="0", mkstream=True)
    except Exception:
        pass

    mock_pool = make_mock_pool()
    with patch("app.workers.consumer.models.batch_upsert_events", new_callable=AsyncMock) as mock_upsert, \
         patch("app.workers.consumer.handle_failure", new_callable=AsyncMock) as mock_fail:
        await handle_batch(fake_redis, mock_pool, [
            ("msg-1", {
                "event_id": event_id,
                "event_type": "purchase",   # invalid type
                "user_id": "",
                "session_id": "sess-1",
                "payload": "{}",
                "client_timestamp": "",
            }),
        ])
        mock_fail.assert_called_once()
        mock_upsert.assert_not_called()


@pytest.mark.asyncio
async def test_handle_batch_mixed_valid_and_invalid(fake_redis):
    """A batch with both valid and invalid events should process valid ones."""
    from app.workers.consumer import handle_batch
    good_id = str(uuid4())
    bad_id = str(uuid4())
    try:
        await fake_redis.xgroup_create("events:raw", "workers", id="0", mkstream=True)
    except Exception:
        pass

    mock_pool = make_mock_pool()
    with patch("app.workers.consumer.models.batch_upsert_events", new_callable=AsyncMock) as mock_upsert, \
         patch("app.workers.consumer.handle_failure", new_callable=AsyncMock), \
         patch("app.workers.consumer.settings") as s:
        s.stream_name = "events:raw"
        s.consumer_group = "workers"
        s.dedup_ttl = 86400
        s.status_cache_ttl = 3600
        await handle_batch(fake_redis, mock_pool, [
            ("msg-1", {
                "event_id": good_id,
                "event_type": "click",
                "user_id": "",
                "session_id": "sess-1",
                "payload": '{"button": "x"}',
                "client_timestamp": "",
            }),
            ("msg-2", {
                "event_id": bad_id,
                "event_type": "unknown_type",
                "user_id": "",
                "session_id": "sess-2",
                "payload": "{}",
                "client_timestamp": "",
            }),
        ])
        # Only the valid event should have been batch-upserted
        mock_upsert.assert_called_once()
        rows = mock_upsert.call_args[0][1]
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# _parse_message / _validate (consumer.py internals)
# ---------------------------------------------------------------------------

def test_parse_message_extracts_fields():
    from app.workers.consumer import _parse_message
    result = _parse_message({
        "event_id": "abc-123",
        "event_type": "click",
        "user_id": "user-1",
        "session_id": "sess-1",
        "payload": '{"button": "x"}',
        "client_timestamp": "2026-04-10T12:00:00",
    })
    assert result["event_id"] == "abc-123"
    assert result["event_type"] == "click"
    assert result["payload"] == {"button": "x"}
    assert result["client_timestamp"] is not None


def test_parse_message_handles_missing_fields():
    from app.workers.consumer import _parse_message
    result = _parse_message({})
    assert result["event_id"] == ""
    assert result["event_type"] == "unknown"
    assert result["user_id"] is None
    assert result["payload"] == {}
    assert result["client_timestamp"] is None


def test_parse_message_handles_invalid_timestamp():
    from app.workers.consumer import _parse_message
    result = _parse_message({
        "event_id": "abc",
        "event_type": "click",
        "client_timestamp": "not-a-date",
        "payload": "{}",
    })
    assert result["client_timestamp"] is None


def test_parse_message_empty_user_id_becomes_none():
    from app.workers.consumer import _parse_message
    result = _parse_message({
        "event_id": "abc",
        "event_type": "click",
        "user_id": "",
        "session_id": "sess-1",
        "payload": "{}",
    })
    assert result["user_id"] is None


def test_validate_accepts_valid_click():
    from app.workers.consumer import _validate
    assert _validate({"event_type": "click", "payload": {}}) is None


def test_validate_accepts_valid_page_view():
    from app.workers.consumer import _validate
    assert _validate({"event_type": "page_view", "payload": {"url": "/home"}}) is None


def test_validate_rejects_unknown_event_type():
    from app.workers.consumer import _validate
    result = _validate({"event_type": "purchase", "payload": {}})
    assert result is not None
    assert "Unknown" in result


def test_validate_rejects_page_view_without_url():
    from app.workers.consumer import _validate
    result = _validate({"event_type": "page_view", "payload": {"referrer": "google.com"}})
    assert result is not None
    assert "url" in result


def test_validate_accepts_session_start():
    from app.workers.consumer import _validate
    assert _validate({"event_type": "session_start", "payload": {}}) is None


def test_validate_accepts_session_end():
    from app.workers.consumer import _validate
    assert _validate({"event_type": "session_end", "payload": {}}) is None
