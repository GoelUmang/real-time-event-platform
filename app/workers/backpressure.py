import redis.asyncio as aioredis
from app.core.config import settings
from app.core.metrics import consumer_group_lag, pending_messages


async def check_backpressure(r: aioredis.Redis) -> bool:
    """Return True if the worker should pause before reading the next batch."""
    try:
        groups = await r.xinfo_groups(settings.stream_name)
        for group in groups:
            if group["name"] == settings.consumer_group:
                lag = group.get("lag") or 0
                pending = group.get("pending") or 0
                consumer_group_lag.labels(group=settings.consumer_group).set(lag)
                pending_messages.labels(group=settings.consumer_group).set(pending)
                if lag > settings.lag_limit or pending > settings.pending_limit:
                    return True
    except Exception:
        pass
    return False
