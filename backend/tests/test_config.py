import pytest

from app.config import Settings


def test_development_defaults_preserve_local_configuration(monkeypatch):
    for name in ("ENVIRONMENT", "DATABASE_URL", "REDIS_URL", "CORS_ORIGINS"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(_env_file=None)

    assert settings.environment == "development"
    assert settings.database_url.endswith("/docintel")
    assert settings.redis_url == "redis://localhost:6379/0"
    assert "http://localhost:3000" in settings.cors_origins


def test_production_requires_external_services_and_authentication(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("API_KEY", "test-api-key")
    with pytest.raises(ValueError, match="DATABASE_URL"):
        Settings(environment="production", _env_file=None)


def test_production_accepts_explicit_configuration():
    settings = Settings(
        environment="production",
        database_url="postgresql+psycopg://user:pass@example.supabase.co:5432/postgres",
        redis_url="redis://example-redis:6379/0",
        openai_api_key="test-key",
        api_key="test-api-key",
        cors_origins="https://frontend.example",
    )

    assert settings.environment == "production"
    assert settings.cors_origins == "https://frontend.example"


def test_production_rejects_wildcard_cors():
    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        Settings(
            environment="production",
            database_url="postgresql+psycopg://user:pass@example.supabase.co:5432/postgres",
            redis_url="redis://example-redis:6379/0",
            openai_api_key="test-key",
            api_key="test-api-key",
            cors_origins="*",
        )


def test_production_demo_mode_does_not_require_redis_default():
    settings = Settings(
        environment="production",
        processing_mode="background",
        storage_backend="supabase",
        database_url="******example.supabase.co:5432/postgres",
        openai_api_key="test-key",
        api_key="test-api-key",
        cors_origins="https://frontend.example",
        supabase_url="https://example.supabase.co",
        supabase_service_role_key="test-service-key",
    )

    assert settings.processing_mode == "background"
    assert settings.storage_backend == "supabase"
