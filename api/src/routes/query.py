"""
/query endpoint — proxies to the query-engine service.

Free tier: 10 queries/month (enforced via Redis counter).
Home/Family/Pro: unlimited.
"""

from __future__ import annotations

import calendar
import datetime
import os

import httpx
from fastapi import APIRouter, HTTPException, Request
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from ..auth import CurrentUser
from ..media import signed_clip_url

router = APIRouter()

_QE_URL = os.getenv("QUERY_ENGINE_URL", "http://query-engine:8001")
_FREE_MONTHLY_LIMIT = 10


class ConversationTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=1000)

    @field_validator("content")
    @classmethod
    def _strip_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("conversation content cannot be empty")
        return value


class QueryRequest(BaseModel):
    question: str
    conversation_history: list[ConversationTurn] | None = Field(
        default=None, max_length=6
    )

    @field_validator("question")
    @classmethod
    def _validate_question(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("question cannot be empty")
        if len(v) > 1000:
            raise ValueError("question too long (max 1000 chars)")
        return v


class QueryResponse(BaseModel):
    answer: str
    clips: list[str]
    confidence: float


async def _check_rate_limit(user: dict, request: Request) -> None:
    if user.get("tier", "free") != "free":
        return
    now = datetime.date.today()
    key = f"rl:query:{user['sub']}:{now.year}:{now.month}"
    redis = request.app.state.redis
    count = await redis.incr(key)
    if count == 1:
        _, days_in_month = calendar.monthrange(now.year, now.month)
        days_left = days_in_month - now.day + 1
        await redis.expire(key, days_left * 86400)
    if count > _FREE_MONTHLY_LIMIT:
        raise HTTPException(
            status_code=429,
            detail=(
                f"free tier: {_FREE_MONTHLY_LIMIT} queries/month limit reached. "
                "upgrade your plan for unlimited queries."
            ),
        )


@router.post("", response_model=QueryResponse)
async def query(
    req: QueryRequest,
    user: CurrentUser,
    request: Request,
) -> QueryResponse:
    await _check_rate_limit(user, request)

    payload = {
        "question": req.question,
        "owner_id": user["sub"],
        "conversation_history": [
            turn.model_dump() for turn in (req.conversation_history or [])
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{_QE_URL}/query", json=payload)
            resp.raise_for_status()
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=504, detail="query engine timed out"
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=(
                exc.response.status_code
                if 400 <= exc.response.status_code < 500
                else 503
            ),
            detail="query engine rejected the request"
            if exc.response.status_code < 500
            else "query engine unavailable",
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503, detail="query engine unavailable"
        ) from exc

    data = resp.json()
    clips = [
        url
        for clip in data["clips"]
        if (url := signed_clip_url(clip)) is not None
    ]
    return QueryResponse(
        answer=data["answer"],
        clips=clips,
        confidence=data["confidence"],
    )
