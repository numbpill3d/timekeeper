"""
/query endpoint — proxies to the query-engine service.

Free tier: 10 queries/month (enforced via Redis counter).
Home/Family/Pro: unlimited.
"""

from __future__ import annotations

import datetime
import math
import os
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException, Request
from omniscient_shared.time import local_now
from pydantic import BaseModel, Field, ValidationError, field_validator

from ..auth import CurrentUser
from ..media import safe_signed_clip_url

router = APIRouter()

_QE_URL = os.getenv("QUERY_ENGINE_URL", "http://query-engine:8001")
_FREE_MONTHLY_LIMIT = 10


def _seconds_until_next_month(now: datetime.datetime | None = None) -> int:
    """Return a TTL that expires at the start of the next calendar month."""
    current = now or local_now()
    if current.month == 12:
        next_month = datetime.date(current.year + 1, 1, 1)
    else:
        next_month = datetime.date(current.year, current.month + 1, 1)
    boundary = datetime.datetime.combine(
        next_month,
        datetime.time.min,
        tzinfo=current.tzinfo,
    )
    return max(1, math.ceil((boundary - current).total_seconds()))


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


class EvidenceOut(BaseModel):
    event_id: str | None = None
    timestamp: datetime.datetime | None = None
    event_type: str | None = None
    action_label: str | None = None
    location_label: str | None = None
    camera_name: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    person_label: str | None = None
    object_label: str | None = None
    object_category: str | None = None
    clip_url: str | None = None


class QueryEvidenceIn(BaseModel):
    """Internal query-engine contract before clip URLs are signed."""

    event_id: str | None = None
    timestamp: datetime.datetime | None = None
    event_type: str | None = None
    action_label: str | None = None
    location_label: str | None = None
    camera_name: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    person_label: str | None = None
    object_label: str | None = None
    object_category: str | None = None
    clip_path: str | None = None


class QueryResponse(BaseModel):
    answer: str = Field(min_length=1, max_length=10000)
    clips: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[EvidenceOut] = Field(default_factory=list, max_length=20)


class UpstreamQueryResponse(BaseModel):
    answer: str = Field(min_length=1, max_length=10000)
    clips: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[QueryEvidenceIn] = Field(default_factory=list, max_length=20)


async def _check_rate_limit(user: dict, request: Request) -> None:
    tier = await request.app.state.db.fetchval(
        "SELECT subscription_tier FROM users WHERE id = $1",
        user["sub"],
    )
    if tier is None:
        raise HTTPException(status_code=401, detail="user not found")
    if tier != "free":
        return
    now = local_now().date()
    key = f"rl:query:{user['sub']}:{now.year}:{now.month}"
    redis = request.app.state.redis
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, _seconds_until_next_month())
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
        async with httpx.AsyncClient(
            timeout=30.0, follow_redirects=False
        ) as client:
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

    try:
        data = UpstreamQueryResponse.model_validate(resp.json())
    except (TypeError, ValueError, ValidationError) as exc:
        raise HTTPException(
            status_code=503, detail="query engine returned an invalid response"
        ) from exc
    clips = [
        url
        for clip in data.clips
        if (url := safe_signed_clip_url(clip)) is not None
    ]
    evidence = [
        EvidenceOut(
            event_id=str(item.event_id) if item.event_id is not None else None,
            timestamp=item.timestamp,
            event_type=item.event_type,
            action_label=item.action_label,
            location_label=item.location_label,
            camera_name=item.camera_name,
            confidence=item.confidence,
            person_label=item.person_label,
            object_label=item.object_label,
            object_category=item.object_category,
            clip_url=safe_signed_clip_url(item.clip_path),
        )
        for item in data.evidence
    ]
    return QueryResponse(
        answer=data.answer,
        clips=clips,
        confidence=data.confidence,
        evidence=evidence,
    )
