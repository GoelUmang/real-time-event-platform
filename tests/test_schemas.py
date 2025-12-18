"""Tests for Pydantic schemas — validate input/output shape at the API boundary."""
import pytest
from datetime import datetime, timezone
from uuid import uuid4
from pydantic import ValidationError

from app.api.schemas import EventPayload, AcceptedResponse, EventResponse


# ---------------------------------------------------------------------------
# EventPayload (input validation)
# ---------------------------------------------------------------------------

def test_event_payload_valid_page_view():
    p = EventPayload(
        event_type="page_view", session_id="sess-1", payload={"url": "/home"}
    )
    assert p.event_type == "page_view"
    assert p.session_id == "sess-1"


def test_event_payload_valid_click():
    p = EventPayload(
        event_type="click", session_id="sess-1", payload={"button": "cta"}
    )
    assert p.event_type == "click"


def test_event_payload_invalid_event_type():
    with pytest.raises(ValidationError):
        EventPayload(
            event_type="purchase", session_id="sess-1", payload={}
        )


def test_event_payload_missing_session_id():
    with pytest.raises(ValidationError):
        EventPayload(event_type="click", payload={"button": "x"})


def test_event_payload_missing_payload():
    with pytest.raises(ValidationError):
        EventPayload(event_type="click", session_id="sess-1")


def test_event_payload_user_id_optional():
    p = EventPayload(
        event_type="click", session_id="sess-1", payload={}, user_id=None
    )
    assert p.user_id is None


def test_event_payload_client_timestamp_optional():
    p = EventPayload(
        event_type="click", session_id="sess-1", payload={}
    )
    assert p.client_timestamp is None


def test_event_payload_accepts_client_timestamp():
    ts = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
    p = EventPayload(
        event_type="click", session_id="sess-1", payload={},
        client_timestamp=ts,
    )
    assert p.client_timestamp == ts


# ---------------------------------------------------------------------------
# AcceptedResponse
# ---------------------------------------------------------------------------

def test_accepted_response_default_message():
    r = AcceptedResponse(event_id=uuid4())
    assert r.message == "accepted"


def test_accepted_response_contains_event_id():
    eid = uuid4()
    r = AcceptedResponse(event_id=eid)
    assert r.event_id == eid


# ---------------------------------------------------------------------------
# EventResponse
# ---------------------------------------------------------------------------

def test_event_response_all_fields():
    now = datetime.now(timezone.utc)
    r = EventResponse(
        event_id=str(uuid4()),
        event_type="page_view",
        status="succeeded",
        session_id="sess-1",
        user_id="user-1",
        payload={"url": "/home"},
        client_timestamp=now,
        retry_count=0,
        failure_reason=None,
        created_at=now,
        processed_at=now,
    )
    assert r.status == "succeeded"
    assert r.retry_count == 0


def test_event_response_nullable_fields():
    now = datetime.now(timezone.utc)
    r = EventResponse(
        event_id=str(uuid4()),
        event_type="click",
        status="received",
        session_id="sess-1",
        user_id=None,
        payload={},
        client_timestamp=None,
        retry_count=0,
        failure_reason=None,
        created_at=now,
        processed_at=None,
    )
    assert r.user_id is None
    assert r.processed_at is None
    assert r.failure_reason is None
