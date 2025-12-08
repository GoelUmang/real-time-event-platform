from datetime import datetime, timezone
from uuid import uuid4, UUID
from fastapi import APIRouter, HTTPException
from app.api.schemas import EventPayload, AcceptedResponse, EventResponse
from app.producer.event_publisher import publish_event
from app.storage import db, models
from app.storage.redis_client import get_redis
from app.core.metrics import events_ingested

router = APIRouter()

# How long the pending marker lives in Redis (seconds).
# Events should be processed well within this window.
_PENDING_TTL = 300


@router.post("/events", status_code=202, response_model=AcceptedResponse)
async def ingest_event(body: EventPayload) -> AcceptedResponse:
    """Validate, stamp, XADD into Redis Streams, return 202.
    No Postgres write on this path — workers own the INSERT.
    """
    event_id = uuid4()
    r = await get_redis()

    await publish_event(
        r, event_id, body.event_type,
        body.user_id, body.session_id, body.payload, body.client_timestamp,
    )
    # Tombstone so GET /events/{id} can return status=received before the worker inserts.
    await r.set(f"pending:{event_id}", "1", ex=_PENDING_TTL)

    events_ingested.labels(event_type=body.event_type).inc()
    return AcceptedResponse(event_id=event_id)


@router.get("/events/{event_id}", response_model=EventResponse)
async def get_event_by_id(event_id: str) -> EventResponse:
    try:
        uid = UUID(event_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid event_id format")

    pool = await db.get_pool()
    event = await models.get_event(pool, uid)
    if event is not None:
        return EventResponse(**{**event, "event_id": str(event["event_id"])})

    # Event not yet in Postgres — check whether it was recently accepted.
    r = await get_redis()
    if await r.get(f"pending:{event_id}"):
        now = datetime.now(timezone.utc)
        return EventResponse(
            event_id=event_id,
            event_type="unknown",
            status="received",
            session_id="",
            user_id=None,
            payload={},
            client_timestamp=None,
            retry_count=0,
            failure_reason=None,
            created_at=now,
            processed_at=None,
        )

    raise HTTPException(status_code=404, detail="Event not found")
