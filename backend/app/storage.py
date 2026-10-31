"""Backend-only document storage for local development and Supabase deployment."""
from contextlib import contextmanager
from pathlib import Path
import os
import tempfile

import httpx

from app.config import get_settings


def _client() -> httpx.Client:
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise RuntimeError("Supabase Storage is not configured")
    headers = {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "apikey": settings.supabase_service_role_key,
    }
    return httpx.Client(base_url=settings.supabase_url.rstrip("/") + "/storage/v1",
                        headers=headers, timeout=120)


def _object_url(bucket: str, object_key: str) -> str:
    return f"object/{bucket}/{object_key.lstrip('/')}"


def upload_file(path: Path, object_key: str, content_type: str | None = None) -> None:
    settings = get_settings()
    with _client() as client, path.open("rb") as source:
        headers = {"x-upsert": "false"}
        if content_type:
            headers["Content-Type"] = content_type
        response = client.post(_object_url(settings.supabase_storage_bucket, object_key),
                               content=source, headers=headers)
        response.raise_for_status()


def download_file(object_key: str, destination: Path) -> None:
    settings = get_settings()
    with _client() as client:
        response = client.get(_object_url(settings.supabase_storage_bucket, object_key))
        response.raise_for_status()
    destination.write_bytes(response.content)


def delete_file(object_key: str) -> None:
    settings = get_settings()
    with _client() as client:
        response = client.request(
            "DELETE",
            f"object/{settings.supabase_storage_bucket}",
            json={"prefixes": [object_key]},
        )
        response.raise_for_status()


@contextmanager
def materialize(storage_path: str, filename: str):
    settings = get_settings()
    if settings.storage_backend == "local":
        yield Path(storage_path)
        return

    suffix = Path(filename).suffix
    fd, temp_name = tempfile.mkstemp(prefix="docintel-", suffix=suffix)
    os.close(fd)
    temp_path = Path(temp_name)
    try:
        download_file(storage_path, temp_path)
        yield temp_path
    finally:
        temp_path.unlink(missing_ok=True)
