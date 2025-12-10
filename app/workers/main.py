import asyncio
import os
from prometheus_client import start_http_server
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.storage.db import get_pool, close_pool
from app.workers.consumer import run_consumer, run_recovery

logger = get_logger("worker_main")


async def main() -> None:
    configure_logging("worker")
    consumer_id = os.environ.get("HOSTNAME", f"worker-{os.getpid()}")
    start_http_server(settings.worker_metrics_port)
    logger.info("worker_metrics_started", port=settings.worker_metrics_port)

    pool = await get_pool()
    try:
        await asyncio.gather(
            run_consumer(consumer_id, pool),
            run_recovery(consumer_id, pool),
        )
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
