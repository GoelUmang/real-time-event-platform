import json
from datetime import datetime
from uuid import UUID
import redis.asyncio as aioredis
from app.core.config import settings
from app.core.metrics import xadd_duration


async def publish_event(
    r: aioredis.Redis,
    event_id: UUID,
    event_type: str,
    user_id: str | None,
    session_id: str,
    payload: dict,
    client_timestamp: datetime | None,
) -> str:
    """XADD all event fields so workers can INSERT without a round-trip to the caller."""
    with xadd_duration.time():
        message_id = await r.xadd(
            settings.stream_name,
            {
                "event_id": str(event_id),
                "event_type": event_type,
                "user_id": user_id or "",
                "session_id": session_id,
                "payload": json.dumps(payload),
                "client_timestamp": client_timestamp.isoformat() if client_timestamp else "",
            },
        )
    return message_id
