"""Send 4 seed events end-to-end to verify the pipeline is working."""
import asyncio
import httpx

SEED_EVENTS = [
    {"event_type": "session_start", "session_id": "seed-sess-001",
     "user_id": "user-seed-1", "payload": {}},
    {"event_type": "page_view", "session_id": "seed-sess-001",
     "user_id": "user-seed-1", "payload": {"url": "/home"}},
    {"event_type": "click", "session_id": "seed-sess-001",
     "user_id": "user-seed-1", "payload": {"button": "signup"}},
    {"event_type": "session_end", "session_id": "seed-sess-001",
     "user_id": "user-seed-1", "payload": {}},
]


async def main() -> None:
    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=5.0) as client:
        for event in SEED_EVENTS:
            resp = await client.post("/events", json=event)
            print(f"{event['event_type']}: {resp.status_code} → {resp.json()}")


if __name__ == "__main__":
    asyncio.run(main())
