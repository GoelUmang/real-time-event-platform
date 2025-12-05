import json
from uuid import UUID
from datetime import datetime
from typing import Sequence
from app.core.metrics import db_batch_commit_duration

CREATE_TABLE_SQL = """
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'event_status') THEN
        CREATE TYPE event_status AS ENUM (
            'received', 'processing', 'retrying', 'succeeded', 'failed'
        );
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS events (
    id               BIGSERIAL PRIMARY KEY,
    event_id         UUID NOT NULL UNIQUE,
    event_type       TEXT NOT NULL,
    user_id          TEXT,
    session_id       TEXT NOT NULL,
    payload          JSONB NOT NULL,
    client_timestamp TIMESTAMPTZ,
    status           event_status NOT NULL DEFAULT 'received',
    retry_count      SMALLINT NOT NULL DEFAULT 0,
    failure_reason   TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_events_status  ON events (status);
CREATE INDEX IF NOT EXISTS idx_events_user    ON events (user_id);
CREATE INDEX IF NOT EXISTS idx_events_created ON events (created_at DESC);
"""


async def run_migrations(pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(CREATE_TABLE_SQL)


async def upsert_event_succeeded(
    pool,
    event_id: str,
    event_type: str,
    user_id: str | None,
    session_id: str,
    payload: dict,
    client_timestamp: datetime | None,
    processed_at: datetime,
) -> None:
    """Insert the event and immediately mark it succeeded in a single statement.
    ON CONFLICT DO NOTHING makes this idempotent for retried stream messages.
    """
    from uuid import UUID as _UUID
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO events
                (event_id, event_type, user_id, session_id, payload,
                 client_timestamp, status, processed_at)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6, 'succeeded', $7)
            ON CONFLICT (event_id) DO NOTHING
            """,
            _UUID(event_id), event_type, user_id or None, session_id,
            json.dumps(payload), client_timestamp, processed_at,
        )


async def batch_upsert_events(
    pool,
    events: Sequence[tuple],
) -> None:
    """Insert a batch of events in one transaction.

    Each tuple: (event_id_str, event_type, user_id, session_id,
                  payload_dict, client_timestamp, processed_at)

    ON CONFLICT DO NOTHING keeps retried messages idempotent.
    """
    rows = [
        (
            UUID(e[0]), e[1], e[2] or None, e[3],
            json.dumps(e[4]), e[5], e[6],
        )
        for e in events
    ]
    with db_batch_commit_duration.time():
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.executemany(
                    """
                    INSERT INTO events
                        (event_id, event_type, user_id, session_id, payload,
                         client_timestamp, status, processed_at)
                    VALUES ($1, $2, $3, $4, $5::jsonb, $6, 'succeeded', $7)
                    ON CONFLICT (event_id) DO NOTHING
                    """,
                    rows,
                )


async def get_event(pool, event_id: UUID) -> dict | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM events WHERE event_id = $1", event_id
        )
    if row is None:
        return None
    result = dict(row)
    if isinstance(result.get("payload"), str):
        result["payload"] = json.loads(result["payload"])
    return result


async def update_event_status(
    pool,
    event_id: UUID,
    status: str,
    processed_at: datetime | None = None,
    failure_reason: str | None = None,
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE events
            SET status         = $2::event_status,
                processed_at   = $3,
                failure_reason = $4
            WHERE event_id = $1
            """,
            event_id, status, processed_at, failure_reason,
        )


async def increment_retry(pool, event_id: UUID, failure_reason: str) -> int:
    async with pool.acquire() as conn:
        retry_count = await conn.fetchval(
            """
            UPDATE events
            SET retry_count    = retry_count + 1,
                failure_reason = $2,
                status         = 'retrying'
            WHERE event_id = $1
            RETURNING retry_count
            """,
            event_id, failure_reason,
        )
    return retry_count or 0
