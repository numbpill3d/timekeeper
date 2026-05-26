"""
Omniscient Home API — port 8000.

REST + WebSocket. All endpoints require JWT bearer auth except /auth/*.
Rate limiting and RBAC enforced per subscription tier (§8.3, §9).
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db import create_pool
from .routes.alerts import router as alerts_router
from .routes.cameras import router as cameras_router
from .routes.events import router as events_router
from .routes.persons import router as persons_router
from .routes.query import router as query_router
from .routes.users import router as users_router
from .ws.stream import router as ws_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db = await create_pool()
    yield
    await app.state.db.close()


app = FastAPI(
    title="Omniscient Home API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users_router, prefix="/auth", tags=["auth"])
app.include_router(cameras_router, prefix="/cameras", tags=["cameras"])
app.include_router(events_router, prefix="/events", tags=["events"])
app.include_router(query_router, prefix="/query", tags=["query"])
app.include_router(alerts_router, prefix="/alerts", tags=["alerts"])
app.include_router(persons_router, prefix="/persons", tags=["persons"])
app.include_router(ws_router, tags=["websocket"])


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
