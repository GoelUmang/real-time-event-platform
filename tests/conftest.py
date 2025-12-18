import pytest
from unittest.mock import AsyncMock, MagicMock
import fakeredis.aioredis


@pytest.fixture
def mock_pool():
    conn = AsyncMock()
    # transaction() must return an async context manager directly (not a coroutine).
    tx_cm = MagicMock()
    tx_cm.__aenter__ = AsyncMock(return_value=None)
    tx_cm.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=tx_cm)

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.acquire.return_value = cm
    pool._conn = conn  # expose conn for test assertions
    return pool


@pytest.fixture
async def fake_redis():
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield r
    await r.aclose()
