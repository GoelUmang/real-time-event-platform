import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch
from uuid import uuid4


@pytest.fixture
async def client():
    from app.api.main import app
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


# ---------------------------------------------------------------------------
# POST /events — happy path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_post_event_returns_202(client):
    """POST /events only needs Redis — no DB write on the hot path."""
    with patch("app.api.routes.get_redis", new_callable=AsyncMock) as mock_redis_fn, \
         patch("app.producer.event_publisher.publish_event", new_callable=AsyncMock):
        mock_r = AsyncMock()
        mock_r.set = AsyncMock()
        mock_redis_fn.return_value = mock_r
        response = await client.post("/events", json={
            "event_type": "page_view",
            "session_id": "sess-abc",
            "payload": {"url": "/home"},
        })
    assert response.status_code == 202
    assert "event_id" in response.json()


@pytest.mark.asyncio
async def test_post_event_response_contains_accepted_message(client):
    """POST /events response includes the 'accepted' message."""
    with patch("app.api.routes.get_redis", new_callable=AsyncMock) as mock_redis_fn, \
         patch("app.producer.event_publisher.publish_event", new_callable=AsyncMock):
        mock_r = AsyncMock()
        mock_r.set = AsyncMock()
        mock_redis_fn.return_value = mock_r
        response = await client.post("/events", json={
            "event_type": "click",
            "session_id": "sess-abc",
            "payload": {"button": "cta"},
        })
    assert response.json()["message"] == "accepted"


@pytest.mark.asyncio
async def test_post_event_returns_unique_event_ids(client):
    """Each POST should return a distinct event_id."""
    ids = []
    for _ in range(3):
        with patch("app.api.routes.get_redis", new_callable=AsyncMock) as mock_redis_fn, \
             patch("app.producer.event_publisher.publish_event", new_callable=AsyncMock):
            mock_r = AsyncMock()
            mock_r.set = AsyncMock()
            mock_redis_fn.return_value = mock_r
            response = await client.post("/events", json={
                "event_type": "page_view",
                "session_id": "sess-abc",
                "payload": {"url": "/home"},
            })
        ids.append(response.json()["event_id"])
    assert len(set(ids)) == 3


@pytest.mark.asyncio
async def test_post_event_click_type_accepted(client):
    """Click events should be accepted without 'url' in payload."""
    with patch("app.api.routes.get_redis", new_callable=AsyncMock) as mock_redis_fn, \
         patch("app.producer.event_publisher.publish_event", new_callable=AsyncMock):
        mock_r = AsyncMock()
        mock_r.set = AsyncMock()
        mock_redis_fn.return_value = mock_r
        response = await client.post("/events", json={
            "event_type": "click",
            "session_id": "sess-abc",
            "payload": {"button": "signup"},
        })
    assert response.status_code == 202


@pytest.mark.asyncio
async def test_post_event_session_start_accepted(client):
    with patch("app.api.routes.get_redis", new_callable=AsyncMock) as mock_redis_fn, \
         patch("app.producer.event_publisher.publish_event", new_callable=AsyncMock):
        mock_r = AsyncMock()
        mock_r.set = AsyncMock()
        mock_redis_fn.return_value = mock_r
        response = await client.post("/events", json={
            "event_type": "session_start",
            "session_id": "sess-abc",
            "payload": {},
        })
    assert response.status_code == 202


@pytest.mark.asyncio
async def test_post_event_session_end_accepted(client):
    with patch("app.api.routes.get_redis", new_callable=AsyncMock) as mock_redis_fn, \
         patch("app.producer.event_publisher.publish_event", new_callable=AsyncMock):
        mock_r = AsyncMock()
        mock_r.set = AsyncMock()
        mock_redis_fn.return_value = mock_r
        response = await client.post("/events", json={
            "event_type": "session_end",
            "session_id": "sess-abc",
            "payload": {},
        })
    assert response.status_code == 202


@pytest.mark.asyncio
async def test_post_event_with_user_id(client):
    """user_id is optional — when provided it should be accepted."""
    with patch("app.api.routes.get_redis", new_callable=AsyncMock) as mock_redis_fn, \
         patch("app.producer.event_publisher.publish_event", new_callable=AsyncMock):
        mock_r = AsyncMock()
        mock_r.set = AsyncMock()
        mock_redis_fn.return_value = mock_r
        response = await client.post("/events", json={
            "event_type": "page_view",
            "session_id": "sess-abc",
            "user_id": "user-42",
            "payload": {"url": "/home"},
        })
    assert response.status_code == 202


@pytest.mark.asyncio
async def test_post_event_with_client_timestamp(client):
    with patch("app.api.routes.get_redis", new_callable=AsyncMock) as mock_redis_fn, \
         patch("app.producer.event_publisher.publish_event", new_callable=AsyncMock):
        mock_r = AsyncMock()
        mock_r.set = AsyncMock()
        mock_redis_fn.return_value = mock_r
        response = await client.post("/events", json={
            "event_type": "page_view",
            "session_id": "sess-abc",
            "payload": {"url": "/home"},
            "client_timestamp": "2026-04-10T12:00:00Z",
        })
    assert response.status_code == 202


@pytest.mark.asyncio
async def test_post_event_null_user_id_accepted(client):
    """Explicitly null user_id should be accepted for anonymous sessions."""
    with patch("app.api.routes.get_redis", new_callable=AsyncMock) as mock_redis_fn, \
         patch("app.producer.event_publisher.publish_event", new_callable=AsyncMock):
        mock_r = AsyncMock()
        mock_r.set = AsyncMock()
        mock_redis_fn.return_value = mock_r
        response = await client.post("/events", json={
            "event_type": "page_view",
            "session_id": "sess-anon",
            "user_id": None,
            "payload": {"url": "/pricing"},
        })
    assert response.status_code == 202


# ---------------------------------------------------------------------------
# POST /events — validation / rejection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_post_event_missing_session_id_returns_422(client):
    response = await client.post("/events", json={"event_type": "page_view"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_post_event_missing_event_type_returns_422(client):
    response = await client.post("/events", json={
        "session_id": "sess-abc",
        "payload": {"url": "/home"},
    })
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_post_event_invalid_event_type_returns_422(client):
    """event_type is a Literal — unknown values must be rejected."""
    response = await client.post("/events", json={
        "event_type": "purchase",
        "session_id": "sess-abc",
        "payload": {},
    })
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_post_event_missing_payload_returns_422(client):
    response = await client.post("/events", json={
        "event_type": "click",
        "session_id": "sess-abc",
    })
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_post_event_empty_body_returns_422(client):
    response = await client.post("/events", json={})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_post_event_non_json_body_returns_422(client):
    response = await client.post("/events", content=b"not json",
                                 headers={"Content-Type": "application/json"})
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /events/{event_id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_event_found_in_postgres_returns_200(client):
    event_id = str(uuid4())
    fake_event = {
        "event_id": event_id,
        "event_type": "page_view",
        "status": "succeeded",
        "session_id": "sess-abc",
        "user_id": None,
        "payload": {"url": "/home"},
        "client_timestamp": None,
        "retry_count": 0,
        "failure_reason": None,
        "created_at": "2026-04-10T00:00:00+00:00",
        "processed_at": None,
    }
    with patch("app.api.routes.db.get_pool", new_callable=AsyncMock) as mock_pool_fn, \
         patch("app.storage.models.get_event", new_callable=AsyncMock,
               return_value=fake_event):
        mock_pool_fn.return_value = AsyncMock()
        response = await client.get(f"/events/{event_id}")
    assert response.status_code == 200
    assert response.json()["event_id"] == event_id


@pytest.mark.asyncio
async def test_get_event_returns_correct_status(client):
    event_id = str(uuid4())
    fake_event = {
        "event_id": event_id,
        "event_type": "click",
        "status": "succeeded",
        "session_id": "sess-x",
        "user_id": "user-1",
        "payload": {"button": "cta"},
        "client_timestamp": None,
        "retry_count": 0,
        "failure_reason": None,
        "created_at": "2026-04-10T00:00:00+00:00",
        "processed_at": "2026-04-10T00:00:01+00:00",
    }
    with patch("app.api.routes.db.get_pool", new_callable=AsyncMock) as mock_pool_fn, \
         patch("app.storage.models.get_event", new_callable=AsyncMock,
               return_value=fake_event):
        mock_pool_fn.return_value = AsyncMock()
        response = await client.get(f"/events/{event_id}")
    assert response.json()["status"] == "succeeded"


@pytest.mark.asyncio
async def test_get_event_failed_status(client):
    """Events that exhausted retries show status=failed."""
    event_id = str(uuid4())
    fake_event = {
        "event_id": event_id,
        "event_type": "page_view",
        "status": "failed",
        "session_id": "sess-z",
        "user_id": None,
        "payload": {"url": "/broken"},
        "client_timestamp": None,
        "retry_count": 3,
        "failure_reason": "timeout",
        "created_at": "2026-04-10T00:00:00+00:00",
        "processed_at": None,
    }
    with patch("app.api.routes.db.get_pool", new_callable=AsyncMock) as mock_pool_fn, \
         patch("app.storage.models.get_event", new_callable=AsyncMock,
               return_value=fake_event):
        mock_pool_fn.return_value = AsyncMock()
        response = await client.get(f"/events/{event_id}")
    assert response.json()["status"] == "failed"
    assert response.json()["failure_reason"] == "timeout"
    assert response.json()["retry_count"] == 3


@pytest.mark.asyncio
async def test_get_event_pending_in_redis_returns_received(client):
    """Event accepted by API but not yet processed: worker hasn't inserted yet.
    GET should return status=received rather than 404."""
    event_id = str(uuid4())
    with patch("app.api.routes.db.get_pool", new_callable=AsyncMock) as mock_pool_fn, \
         patch("app.storage.models.get_event", new_callable=AsyncMock, return_value=None), \
         patch("app.api.routes.get_redis", new_callable=AsyncMock) as mock_redis_fn:
        mock_pool_fn.return_value = AsyncMock()
        mock_r = AsyncMock()
        mock_r.get.return_value = "1"   # pending:{event_id} exists
        mock_redis_fn.return_value = mock_r
        response = await client.get(f"/events/{event_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "received"


@pytest.mark.asyncio
async def test_get_event_not_found_returns_404(client):
    event_id = str(uuid4())
    with patch("app.api.routes.db.get_pool", new_callable=AsyncMock) as mock_pool_fn, \
         patch("app.storage.models.get_event", new_callable=AsyncMock, return_value=None), \
         patch("app.api.routes.get_redis", new_callable=AsyncMock) as mock_redis_fn:
        mock_pool_fn.return_value = AsyncMock()
        mock_r = AsyncMock()
        mock_r.get.return_value = None   # not in Redis either
        mock_redis_fn.return_value = mock_r
        response = await client.get(f"/events/{event_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_event_invalid_uuid_returns_400(client):
    with patch("app.api.routes.db.get_pool", new_callable=AsyncMock):
        response = await client.get("/events/not-a-uuid")
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Metrics endpoint
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_metrics_endpoint_returns_200(client):
    response = await client.get("/metrics/")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_metrics_endpoint_contains_prometheus_data(client):
    response = await client.get("/metrics/")
    body = response.text
    assert "events_ingested_total" in body or "HELP" in body
