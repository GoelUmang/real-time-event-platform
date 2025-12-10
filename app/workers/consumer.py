import asyncio
import json
from datetime import datetime, timezone
import redis.asyncio as aioredis
from app.core.config import settings
from app.core.logging import get_logger
from app.core.metrics import events_processed, batch_size_histogram
from app.storage import models
from app.workers.backpressure import check_backpressure
from app.workers.processor import VALID_EVENT_TYPES
from app.workers.retry_policy import handle_failure

logger = get_logger("consumer")


def _parse_message(data: dict) -> dict:
    """Extract and coerce all fields from a raw stream message dict."""
    raw_ts = data.get("client_timestamp", "")
    client_timestamp = None
    if raw_ts:
        try:
            client_timestamp = datetime.fromisoformat(raw_ts)
        except ValueError:
            pass
    return {
        "event_id": data.get("event_id", ""),
        "event_type": data.get("event_type", "unknown"),
        "user_id": data.get("user_id") or None,
        "session_id": data.get("session_id", ""),
        "payload": json.loads(data.get("payload", "{}")),
        "client_timestamp": client_timestamp,
    }


async def run_consumer(consumer_id: str, pool) -> None:
    r = aioredis.from_url(settings.redis_url, decode_responses=True)

    try:
        await r.xgroup_create(
            settings.stream_name, settings.consumer_group, id="0", mkstream=True
        )
    except Exception:
        pass  # group already exists

    logger.info("consumer_started", consumer_id=consumer_id)

    while True:
        if await check_backpressure(r):
            await asyncio.sleep(0.5)
            continue

        messages = await r.xreadgroup(
            settings.consumer_group,
            consumer_id,
            {settings.stream_name: ">"},
            count=settings.worker_batch_size,
            block=settings.worker_block_ms,
        )

        if not messages:
            continue

        for _stream, raw_batch in messages:
            await handle_batch(r, pool, raw_batch)


async def handle_batch(
    r: aioredis.Redis,
    pool,
    raw_batch: list[tuple[str, dict]],
) -> None:
    """Process a full XREADGROUP batch in as few DB round-trips as possible.

    Strategy:
    - Dedup-check all messages up front (individual Redis GETs).
    - Validate all non-duplicate events; dead-letter validation failures immediately.
    - Batch-INSERT valid events in one transaction.
    - XACK all message IDs (duplicates + successes + validation failures).
    - For transient errors (DB failure), ACK is skipped for the failed batch
      so XCLAIM recovery can retry the whole batch.
    """
    now = datetime.now(timezone.utc)
    parsed = [(msg_id, _parse_message(data)) for msg_id, data in raw_batch]
    batch_size_histogram.observe(len(parsed))

    # --- dedup pass ---
    to_process: list[tuple[str, dict]] = []   # (message_id, event)
    dup_ids: list[str] = []

    for msg_id, evt in parsed:
        if await r.get(f"dedup:{evt['event_id']}"):
            dup_ids.append(msg_id)
            logger.info("duplicate_skipped", event_id=evt["event_id"])
        else:
            to_process.append((msg_id, evt))

    if dup_ids:
        await r.xack(settings.stream_name, settings.consumer_group, *dup_ids)

    if not to_process:
        return

    # --- validation pass ---
    valid: list[tuple[str, dict]] = []
    invalid_ids: list[str] = []

    for msg_id, evt in to_process:
        reason = _validate(evt)
        if reason:
            invalid_ids.append(msg_id)
            asyncio.create_task(
                handle_failure(
                    r, evt["event_id"], evt["event_type"],
                    evt["user_id"], evt["session_id"],
                    evt["payload"], evt["client_timestamp"], reason,
                )
            )
            events_processed.labels(status="failed").inc()
        else:
            valid.append((msg_id, evt))

    if invalid_ids:
        await r.xack(settings.stream_name, settings.consumer_group, *invalid_ids)

    if not valid:
        return

    # --- batch DB insert ---
    rows = [
        (
            evt["event_id"], evt["event_type"], evt["user_id"],
            evt["session_id"], evt["payload"], evt["client_timestamp"], now,
        )
        for _, evt in valid
    ]
    try:
        await models.batch_upsert_events(pool, rows)
    except Exception as exc:
        # Transient DB failure — do NOT ACK; XCLAIM recovery will retry.
        logger.error("batch_insert_failed", error=str(exc), batch_size=len(valid))
        return

    # --- post-insert: set dedup keys + status cache, XACK all ---
    valid_ids = [msg_id for msg_id, _ in valid]
    pipe = r.pipeline(transaction=False)
    for _, evt in valid:
        pipe.set(f"dedup:{evt['event_id']}", "1", ex=settings.dedup_ttl)
        pipe.set(f"status:{evt['event_id']}", "succeeded", ex=settings.status_cache_ttl)
    await pipe.execute()

    await r.xack(settings.stream_name, settings.consumer_group, *valid_ids)
    events_processed.labels(status="succeeded").inc(len(valid_ids))
    logger.info("batch_processed", count=len(valid_ids))


def _validate(evt: dict) -> str | None:
    """Return an error string if the event fails validation, else None."""
    if evt["event_type"] not in VALID_EVENT_TYPES:
        return f"Unknown event_type: {evt['event_type']}"
    if evt["event_type"] == "page_view" and "url" not in evt["payload"]:
        return "page_view requires 'url' in payload"
    return None


# ---------------------------------------------------------------------------
# XCLAIM recovery — reclaims messages stuck in the PEL after a worker crash
# ---------------------------------------------------------------------------

_CLAIM_IDLE_MS = 30_000   # reclaim messages idle for > 30 s
_RECOVERY_INTERVAL = 15   # check every 15 s


async def run_recovery(consumer_id: str, pool) -> None:
    """Periodically scan the PEL and re-process messages idle longer than
    _CLAIM_IDLE_MS.  Runs as a sibling task alongside run_consumer."""
    r = aioredis.from_url(settings.redis_url, decode_responses=True)
    recovery_consumer = f"{consumer_id}-recovery"
    logger.info("recovery_started", consumer_id=recovery_consumer)

    while True:
        await asyncio.sleep(_RECOVERY_INTERVAL)
        try:
            # XAUTOCLAIM returns (next_id, claimed_messages, deleted_ids)
            _, claimed, _ = await r.xautoclaim(
                settings.stream_name,
                settings.consumer_group,
                recovery_consumer,
                min_idle_time=_CLAIM_IDLE_MS,
                start_id="0-0",
                count=settings.worker_batch_size,
            )
            if claimed:
                logger.info("recovery_claimed", count=len(claimed))
                await handle_batch(r, pool, claimed)
        except Exception as exc:
            logger.warning("recovery_error", error=str(exc))
