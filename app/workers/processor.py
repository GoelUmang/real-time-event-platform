from datetime import datetime, timezone
import redis.asyncio as aioredis
from app.core.config import settings
from app.core.logging import get_logger
from app.core.metrics import processing_duration
from app.storage import models

logger = get_logger("processor")

VALID_EVENT_TYPES = {"page_view", "click", "session_start", "session_end"}


async def process_event(
    pool,
    r: aioredis.Redis,
    event_id: str,
    event_type: str,
    user_id: str | None,
    session_id: str,
    payload: dict,
    client_timestamp: datetime | None,
) -> None:
    """Validate, INSERT the event, mark succeeded — all in one DB round-trip."""
    if event_type not in VALID_EVENT_TYPES:
        raise ValueError(f"Unknown event_type: {event_type}")

    if event_type == "page_view" and "url" not in payload:
        raise ValueError("page_view requires 'url' in payload")

    with processing_duration.labels(event_type=event_type).time():
        now = datetime.now(timezone.utc)
        await models.upsert_event_succeeded(
            pool, event_id, event_type, user_id, session_id, payload,
            client_timestamp, processed_at=now,
        )
        await r.set(f"status:{event_id}", "succeeded", ex=settings.status_cache_ttl)

    logger.info("event_processed", event_id=event_id, event_type=event_type)
