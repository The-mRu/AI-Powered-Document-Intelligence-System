"""All configuration comes from environment variables (12-factor); nothing is hard-coded."""
from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    environment: str = "development"
    processing_mode: str = "celery"
    storage_backend: str = "local"
    database_url: str = "postgresql+psycopg://app:app@localhost:5432/docintel"
    redis_url: str = "redis://localhost:6379/0"
    storage_dir: str = "/storage"
    supabase_url: str | None = None
    supabase_service_role_key: str | None = Field(default=None, repr=False)
    supabase_storage_bucket: str = "documents"
    max_upload_mb: int = 500
    max_files_per_request: int = 20
    cors_origins: str = "http://localhost:3000,http://localhost:5173"
    openai_api_key: str | None = Field(default=None, repr=False)
    openai_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def validate_environment(self):
        environment = self.environment.lower()
        if environment not in {"development", "production"}:
            raise ValueError("ENVIRONMENT must be 'development' or 'production'")
        if self.processing_mode not in {"celery", "background"}:
            raise ValueError("PROCESSING_MODE must be 'celery' or 'background'")
        if self.storage_backend not in {"local", "supabase"}:
            raise ValueError("STORAGE_BACKEND must be 'local' or 'supabase'")
        if environment == "production":
            if self.database_url == type(self).model_fields["database_url"].default:
                raise ValueError("DATABASE_URL must be set when ENVIRONMENT=production")
            if self.processing_mode == "celery" and self.redis_url == type(self).model_fields["redis_url"].default:
                raise ValueError("REDIS_URL must be set when ENVIRONMENT=production")
            if not self.openai_api_key:
                raise ValueError("OPENAI_API_KEY must be set when ENVIRONMENT=production")
            if self.storage_backend == "supabase" and (
                not self.supabase_url or not self.supabase_service_role_key
            ):
                raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required for Supabase Storage")
            origins = [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]
            if not origins or "*" in origins:
                raise ValueError("CORS_ORIGINS must contain explicit origins in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
