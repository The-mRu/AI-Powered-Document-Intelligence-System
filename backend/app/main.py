import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
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
                   allow_methods=["GET", "POST", "PATCH"], allow_headers=["*"])
app.include_router(router)


@app.get("/health")
def health():
    with get_engine().connect() as c:
        c.execute(text("SELECT 1"))
    return {"status": "ok"}
