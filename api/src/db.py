"""Asyncpg connection pool, injected as a FastAPI dependency."""

from __future__ import annotations

import os

import asyncpg
from fastapi import Request

_DB_URL = os.getenv("DATABASE_URL", "")
_DB_CONNECT_TIMEOUT_SECONDS = 15


async def create_pool() -> asyncpg.Pool:
    return await asyncpg.create_pool(
        _DB_URL,
        min_size=2,
        max_size=10,
        timeout=_DB_CONNECT_TIMEOUT_SECONDS,
    )


async def get_db(request: Request) -> asyncpg.Connection:
    async with request.app.state.db.acquire() as conn:
        yield conn
