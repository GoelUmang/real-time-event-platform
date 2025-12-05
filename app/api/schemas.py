from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Literal


class EventPayload(BaseModel):
    event_type: Literal["page_view", "click", "session_start", "session_end"]
    user_id: str | None = None
    session_id: str
    payload: dict
    client_timestamp: datetime | None = None


class AcceptedResponse(BaseModel):
    event_id: UUID
    message: str = "accepted"


class EventResponse(BaseModel):
    event_id: str
    event_type: str
    status: str
    session_id: str
    user_id: str | None
    payload: dict
    client_timestamp: datetime | None
    retry_count: int
    failure_reason: str | None
    created_at: datetime
    processed_at: datetime | None
