import asyncio
import json
from datetime import datetime
import redis.asyncio as aioredis
from app.core.config import settings
from app.core.logging import get_logger
from app.core.metrics import events_retry_total, events_dead_lettered

logger = get_logger("retry_policy")

_RETRY_COUNT_TTL = 86400  # 24 h — matches dedup TTL


async def handle_failure(
    r: aioredis.Redis,
    event_id: str,
    event_type: str,
    user_id: str | None,
    session_id: str,
    payload: dict,
    client_timestamp: datetime | None,
    reason: str,
) -> None:
    """Track retry count in Redis (row may not exist in Postgres yet) and
    either schedule a re-queue or dead-letter the event."""
    retry_key = f"retry_count:{event_id}"
    retry_count = await r.incr(retry_key)
    await r.expire(retry_key, _RETRY_COUNT_TTL)
    events_retry_total.labels(event_type=event_type).inc()

    if retry_count < settings.max_retries:
        backoff = min(2 ** retry_count, 60)
        asyncio.create_task(
            delayed_requeue(
                r, event_id, event_type, user_id, session_id,
                payload, client_timestamp, backoff,
            )
        )
        logger.info("retry_scheduled",
                    event_id=event_id, retry_count=retry_count, backoff=backoff)
    else:
        await r.xadd(
            settings.dead_letter_stream,
            {
                "event_id": event_id,
                "event_type": event_type,
                "failure_reason": reason,
                "retry_count": str(retry_count),
            },
        )
        events_dead_lettered.labels(event_type=event_type).inc()
        logger.error("event_dead_lettered",
                     event_id=event_id, retry_count=retry_count, reason=reason)


async def delayed_requeue(
    r: aioredis.Redis,
    event_id: str,
    event_type: str,
    user_id: str | None,
    session_id: str,
    payload: dict,
    client_timestamp: datetime | None,
    backoff: int,
) -> None:
    """Sleep backoff seconds then re-publish the original event data to the stream."""
    await asyncio.sleep(backoff)
    await r.xadd(
        settings.stream_name,
        {
            "event_id": event_id,
            "event_type": event_type,
            "user_id": user_id or "",
            "session_id": session_id,
            "payload": json.dumps(payload),
            "client_timestamp": client_timestamp.isoformat() if client_timestamp else "",
        },
    )
    logger.info("event_requeued", event_id=event_id, backoff=backoff)
