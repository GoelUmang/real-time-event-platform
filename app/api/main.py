from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app
from app.api.routes import router
from app.storage import db, models
from app.storage.redis_client import close_redis
from app.core.logging import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging("api")
    pool = await db.get_pool()
    await models.run_migrations(pool)
    yield
    await db.close_pool()
    await close_redis()


app = FastAPI(title="Real-Time Event Platform", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)
