import secrets

from fastapi import Header, HTTPException

from app.config import get_settings


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Require the owner key when API_KEY is configured."""
    expected = get_settings().api_key
    if expected and not (x_api_key and secrets.compare_digest(x_api_key, expected)):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
