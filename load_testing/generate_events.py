"""
Send events to the API at a target rate using concurrent async workers.

The old implementation was serial (one request at a time), which capped
throughput at ~1/RTT regardless of the target rate. This version uses
a token-bucket filled at `rate` tokens/sec consumed by `concurrency`
parallel workers, so it can actually saturate the server.

Usage:
    python load_testing/generate_events.py --rate 5000 --duration 20
    python load_testing/generate_events.py --rate 10000 --duration 20 --concurrency 500
"""
import asyncio
import argparse
import random
from typing import Optional
import httpx
from uuid import uuid4

EVENT_TYPES = ["page_view", "click", "session_start", "session_end"]
URLS = ["/home", "/about", "/products", "/checkout", "/profile"]


def random_event() -> dict:
    event_type = random.choice(EVENT_TYPES)
    payload = {"url": random.choice(URLS)} if event_type == "page_view" else {"button": "cta"}
    return {
        "event_type": event_type,
        "user_id": f"user-{random.randint(1, 1000)}",
        "session_id": str(uuid4()),
        "payload": payload,
    }


async def send_events(
    rate: int,
    duration: int,
    base_url: str,
    concurrency: Optional[int] = None,
) -> dict:
    """
    Fire requests concurrently at up to `rate` events/sec for `duration` seconds.

    `concurrency` controls how many requests can be in-flight simultaneously.
    Default: min(rate, 500) — enough to saturate most single-node setups.
    """
    if concurrency is None:
        concurrency = min(rate, 500)

    sent = 0
    errors = 0
    stop = asyncio.Event()

    # Token bucket: refilled at `rate` tokens/sec; max 2 seconds of burst headroom.
    bucket: asyncio.Queue[int] = asyncio.Queue(maxsize=rate * 2)

    async def filler() -> None:
        interval = 1.0 / rate
        while not stop.is_set():
            try:
                bucket.put_nowait(1)
            except asyncio.QueueFull:
                pass
            await asyncio.sleep(interval)

    async def worker(client: httpx.AsyncClient) -> None:
        nonlocal sent, errors
        while not stop.is_set():
            try:
                await asyncio.wait_for(bucket.get(), timeout=0.2)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                continue
            try:
                resp = await client.post("/events", json=random_event())
                if resp.status_code == 202:
                    sent += 1
                else:
                    errors += 1
            except Exception:
                errors += 1

    limits = httpx.Limits(
        max_connections=concurrency + 20,
        max_keepalive_connections=concurrency,
    )
    async with httpx.AsyncClient(base_url=base_url, timeout=10.0, limits=limits) as client:
        filler_task = asyncio.create_task(filler())
        worker_tasks = [asyncio.create_task(worker(client)) for _ in range(concurrency)]

        await asyncio.sleep(duration)
        stop.set()

        await asyncio.gather(*worker_tasks, return_exceptions=True)
        filler_task.cancel()
        try:
            await filler_task
        except asyncio.CancelledError:
            pass

    return {"sent": sent, "errors": errors, "duration": duration, "rate": rate}


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rate", type=int, default=1000)
    parser.add_argument("--duration", type=int, default=30)
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--concurrency", type=int, default=None)
    args = parser.parse_args()

    print(f"Sending up to {args.rate} events/sec for {args.duration}s → {args.url}")
    result = await send_events(args.rate, args.duration, args.url, args.concurrency)
    actual = result["sent"] / args.duration
    print(f"Done — sent={result['sent']}  errors={result['errors']}  actual={actual:.0f} e/s")


if __name__ == "__main__":
    asyncio.run(main())
