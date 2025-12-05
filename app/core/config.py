from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://events_user:events_pass@localhost:5432/events_db"
    db_pool_min_size: int = 2
    db_pool_max_size: int = 20
    redis_url: str = "redis://localhost:6379"
    stream_name: str = "events:raw"
    dead_letter_stream: str = "events:dead"
    consumer_group: str = "workers"
    worker_batch_size: int = 10
    worker_block_ms: int = 1000
    max_retries: int = 3
    lag_limit: int = 1000
    pending_limit: int = 500
    dedup_ttl: int = 86400
    status_cache_ttl: int = 3600
    worker_metrics_port: int = 8001
    rate_limit_per_second: int = 100


settings = Settings()
