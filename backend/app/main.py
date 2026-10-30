import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.documents import router
from app.config import get_settings
from app.db.session import get_engine, init_db

log = logging.getLogger("docintel")


@asynccontextmanager
async def lifespan(_: FastAPI):
    for attempt in range(15):  # the database container may still be starting
        try:
            init_db()
            break
        except Exception as e:
            log.warning("database not ready (%s), retrying...", type(e).__name__)
            time.sleep(2)
    else:
        raise RuntimeError("Database unavailable after retries")
    yield


app = FastAPI(title="Document Intelligence API", version="1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
                   allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["*"])
app.include_router(router)


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
    upload = schema.get("components", {}).get("schemas", {}).get(
        "Body_upload_documents_api_documents_post", {}
    )
    item = upload.get("properties", {}).get("files", {}).get("items", {})
    if item.get("contentMediaType") == "application/octet-stream":
        item["format"] = "binary"
    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi


@app.get("/health")
def health():
    with get_engine().connect() as c:
        c.execute(text("SELECT 1"))
    return {"status": "ok"}
