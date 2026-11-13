"""
Omniscient Home API — port 8000.

REST + WebSocket. All endpoints require JWT bearer auth except /auth/*.
Rate limiting and RBAC enforced per subscription tier.
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .db import create_pool
from .routes.alerts import router as alerts_router
from .routes.audit import router as audit_router
from .routes.cameras import router as cameras_router
from .routes.events import router as events_router
from .routes.persons import router as persons_router
from .routes.pipedream import router as pipedream_router
from .routes.query import router as query_router
from .routes.users import router as users_router
from .ws.stream import router as ws_router

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

_REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")


def _parse_allowed_origins(raw: str | None) -> list[str]:
    """Return explicit CORS origins; credentials must never use ``*``."""
    origins = [origin.strip() for origin in (raw or "").split(",") if origin.strip()]
    if not origins:
        return ["http://localhost:3000", "http://127.0.0.1:3000"]
    if "*" in origins:
        raise RuntimeError(
            "ALLOWED_ORIGINS cannot contain '*' while credentialed requests are enabled"
        )
    return origins


_ALLOWED_ORIGINS = _parse_allowed_origins(os.getenv("ALLOWED_ORIGINS"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db = await create_pool()
    app.state.redis = aioredis.from_url(_REDIS_URL, decode_responses=True)
    yield
    await app.state.db.close()
    await app.state.redis.aclose()


app = FastAPI(
    title="Omniscient Home API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    t = time.perf_counter()
    response = await call_next(request)
    ms = (time.perf_counter() - t) * 1000
    log.info(
        "%s %s %s %.0fms",
        request.method, request.url.path, response.status_code, ms,
    )
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    log.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "internal server error"})

app.include_router(users_router, prefix="/auth", tags=["auth"])
app.include_router(cameras_router, prefix="/cameras", tags=["cameras"])
app.include_router(events_router, prefix="/events", tags=["events"])
app.include_router(query_router, prefix="/query", tags=["query"])
app.include_router(alerts_router, prefix="/alerts", tags=["alerts"])
app.include_router(audit_router, prefix="/audit", tags=["audit"])
app.include_router(persons_router, prefix="/persons", tags=["persons"])
app.include_router(pipedream_router, tags=["integrations"])
app.include_router(ws_router, tags=["websocket"])


@app.get("/health")
async def health() -> dict:
    try:
        await app.state.db.fetchval("SELECT 1")
        await app.state.redis.ping()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="dependency unavailable") from exc
    return {"status": "ok", "database": "ok", "redis": "ok"}
