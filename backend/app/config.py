"""All configuration comes from environment variables (12-factor); nothing is hard-coded."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://app:app@localhost:5432/docintel"
    redis_url: str = "redis://localhost:6379/0"
    storage_dir: str = "/storage"
    max_upload_mb: int = 500
    max_files_per_request: int = 20
    api_key: str | None = None  # set in production: every /api call then needs X-API-Key
    cors_origins: str = "http://localhost:3000,http://localhost:5173"
    openai_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
