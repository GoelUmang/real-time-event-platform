"""Tests for the event publisher — XADD to Redis Streams."""
import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone
from uuid import uuid4


@pytest.mark.asyncio
async def test_publish_event_calls_xadd(fake_redis):
    from app.producer.event_publisher import publish_event
    event_id = uuid4()
    msg_id = await publish_event(
        fake_redis, event_id, "page_view",
        "user-1", "sess-1", {"url": "/home"}, None,
    )
    assert msg_id is not None


@pytest.mark.asyncio
async def test_publish_event_writes_to_correct_stream(fake_redis):
    from app.producer.event_publisher import publish_event
    event_id = uuid4()
    await publish_event(
        fake_redis, event_id, "click",
        None, "sess-1", {"button": "x"}, None,
    )
    length = await fake_redis.xlen("events:raw")
    assert length >= 1


@pytest.mark.asyncio
async def test_publish_event_includes_event_id(fake_redis):
    from app.producer.event_publisher import publish_event
    event_id = uuid4()
    await publish_event(
        fake_redis, event_id, "page_view",
        "user-1", "sess-1", {"url": "/about"}, None,
    )
    msgs = await fake_redis.xrange("events:raw")
    _, data = msgs[-1]
    assert data["event_id"] == str(event_id)


@pytest.mark.asyncio
async def test_publish_event_with_client_timestamp(fake_redis):
    from app.producer.event_publisher import publish_event
    event_id = uuid4()
    ts = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
    await publish_event(
        fake_redis, event_id, "page_view",
        "user-1", "sess-1", {"url": "/home"}, ts,
    )
    msgs = await fake_redis.xrange("events:raw")
    _, data = msgs[-1]
    assert data["client_timestamp"] != ""


@pytest.mark.asyncio
async def test_publish_event_without_timestamp_sends_empty(fake_redis):
    from app.producer.event_publisher import publish_event
    event_id = uuid4()
    await publish_event(
        fake_redis, event_id, "click",
        None, "sess-1", {"button": "x"}, None,
    )
    msgs = await fake_redis.xrange("events:raw")
    _, data = msgs[-1]
    assert data["client_timestamp"] == ""


@pytest.mark.asyncio
async def test_publish_event_null_user_id_sends_empty_string(fake_redis):
    from app.producer.event_publisher import publish_event
    event_id = uuid4()
    await publish_event(
        fake_redis, event_id, "click",
        None, "sess-1", {"button": "x"}, None,
    )
    msgs = await fake_redis.xrange("events:raw")
    _, data = msgs[-1]
    assert data["user_id"] == ""


@pytest.mark.asyncio
async def test_publish_event_serialises_payload_as_json(fake_redis):
    import json
    from app.producer.event_publisher import publish_event
    event_id = uuid4()
    payload = {"url": "/checkout", "items": 5}
    await publish_event(
        fake_redis, event_id, "page_view",
        "user-1", "sess-1", payload, None,
    )
    msgs = await fake_redis.xrange("events:raw")
    _, data = msgs[-1]
    assert json.loads(data["payload"]) == payload
