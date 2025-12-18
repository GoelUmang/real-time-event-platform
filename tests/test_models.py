import json
import pytest
from datetime import datetime, timezone
from uuid import uuid4


# ---------------------------------------------------------------------------
# upsert_event_succeeded
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_upsert_event_succeeded_executes_sql(mock_pool):
    from app.storage.models import upsert_event_succeeded
    now = datetime.now(timezone.utc)
    await upsert_event_succeeded(
        mock_pool, str(uuid4()), "page_view", "user-1", "sess-1",
        {"url": "/home"}, None, now,
    )
    mock_pool._conn.execute.assert_called_once()


@pytest.mark.asyncio
async def test_upsert_event_succeeded_with_null_user_id(mock_pool):
    from app.storage.models import upsert_event_succeeded
    now = datetime.now(timezone.utc)
    await upsert_event_succeeded(
        mock_pool, str(uuid4()), "click", None, "sess-anon",
        {"button": "x"}, None, now,
    )
    mock_pool._conn.execute.assert_called_once()


@pytest.mark.asyncio
async def test_upsert_event_succeeded_with_client_timestamp(mock_pool):
    from app.storage.models import upsert_event_succeeded
    now = datetime.now(timezone.utc)
    ts = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
    await upsert_event_succeeded(
        mock_pool, str(uuid4()), "page_view", "user-1", "sess-1",
        {"url": "/about"}, ts, now,
    )
    mock_pool._conn.execute.assert_called_once()


@pytest.mark.asyncio
async def test_upsert_event_succeeded_passes_json_payload(mock_pool):
    """Payload should be serialised to JSON string for the $5::jsonb parameter."""
    from app.storage.models import upsert_event_succeeded
    now = datetime.now(timezone.utc)
    payload = {"url": "/checkout", "items": 3}
    await upsert_event_succeeded(
        mock_pool, str(uuid4()), "page_view", "user-1", "sess-1",
        payload, None, now,
    )
    call_args = mock_pool._conn.execute.call_args
    # 5th positional arg (index 4) should be the JSON-serialised payload
    assert json.loads(call_args[0][5]) == payload


# ---------------------------------------------------------------------------
# batch_upsert_events
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_batch_upsert_events_executes_in_transaction(mock_pool):
    from app.storage.models import batch_upsert_events
    now = datetime.now(timezone.utc)
    rows = [
        (str(uuid4()), "page_view", "user-1", "sess-1", {"url": "/a"}, None, now),
        (str(uuid4()), "click",     "user-2", "sess-2", {"btn": "x"}, None, now),
    ]
    await batch_upsert_events(mock_pool, rows)
    # executemany called once inside the transaction
    mock_pool._conn.executemany.assert_called_once()


@pytest.mark.asyncio
async def test_batch_upsert_single_event(mock_pool):
    """Batch upsert should work with a single event."""
    from app.storage.models import batch_upsert_events
    now = datetime.now(timezone.utc)
    rows = [
        (str(uuid4()), "click", "user-1", "sess-1", {"button": "cta"}, None, now),
    ]
    await batch_upsert_events(mock_pool, rows)
    mock_pool._conn.executemany.assert_called_once()


@pytest.mark.asyncio
async def test_batch_upsert_large_batch(mock_pool):
    """Batch upsert should handle larger batches."""
    from app.storage.models import batch_upsert_events
    now = datetime.now(timezone.utc)
    rows = [
        (str(uuid4()), "click", f"user-{i}", f"sess-{i}", {"i": i}, None, now)
        for i in range(10)
    ]
    await batch_upsert_events(mock_pool, rows)
    mock_pool._conn.executemany.assert_called_once()
    # Verify the correct number of rows was passed
    call_args = mock_pool._conn.executemany.call_args
    assert len(call_args[0][1]) == 10


# ---------------------------------------------------------------------------
# get_event
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_event_returns_none_when_missing(mock_pool):
    from app.storage.models import get_event
    mock_pool._conn.fetchrow.return_value = None
    result = await get_event(mock_pool, uuid4())
    assert result is None


@pytest.mark.asyncio
async def test_get_event_returns_dict_when_found(mock_pool):
    """When a row is found, get_event should return a dict."""
    from app.storage.models import get_event
    from unittest.mock import MagicMock

    fake_row = MagicMock()
    fake_row.__iter__ = MagicMock(return_value=iter([
        ("event_id", uuid4()), ("event_type", "click"),
        ("status", "succeeded"), ("payload", '{"button": "x"}'),
    ]))
    fake_row.keys = MagicMock(return_value=["event_id", "event_type", "status", "payload"])
    fake_row.__getitem__ = lambda self, key: dict(list(self.__iter__()))[key]

    # Simulate asyncpg Record by making dict(row) work
    mock_pool._conn.fetchrow.return_value = {
        "event_id": str(uuid4()),
        "event_type": "click",
        "status": "succeeded",
        "payload": '{"button": "x"}',
    }
    result = await get_event(mock_pool, uuid4())
    assert result is not None
    assert result["event_type"] == "click"
    assert result["payload"] == {"button": "x"}


# ---------------------------------------------------------------------------
# update_event_status
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_event_status_calls_execute(mock_pool):
    from app.storage.models import update_event_status
    await update_event_status(mock_pool, uuid4(), "failed", failure_reason="timeout")
    mock_pool._conn.execute.assert_called_once()


@pytest.mark.asyncio
async def test_update_event_status_to_succeeded(mock_pool):
    from app.storage.models import update_event_status
    now = datetime.now(timezone.utc)
    await update_event_status(mock_pool, uuid4(), "succeeded", processed_at=now)
    mock_pool._conn.execute.assert_called_once()


# ---------------------------------------------------------------------------
# increment_retry
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_increment_retry_calls_execute(mock_pool):
    from app.storage.models import increment_retry
    mock_pool._conn.fetchval.return_value = 1
    result = await increment_retry(mock_pool, uuid4(), "timeout")
    assert result == 1
    mock_pool._conn.fetchval.assert_called_once()


@pytest.mark.asyncio
async def test_increment_retry_returns_zero_when_null(mock_pool):
    """If the event doesn't exist, fetchval returns None → should return 0."""
    from app.storage.models import increment_retry
    mock_pool._conn.fetchval.return_value = None
    result = await increment_retry(mock_pool, uuid4(), "not found")
    assert result == 0
