"""
/query endpoint — proxies to the query-engine service.

Free tier: 10 queries/month (enforced via Redis counter).
Home/Family/Pro: unlimited.
"""

from __future__ import annotations

import os
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..auth import CurrentUser

router = APIRouter()

_QE_URL = os.getenv("QUERY_ENGINE_URL", "http://query-engine:8001")


class QueryRequest(BaseModel):
    question: str
    conversation_history: list[dict] | None = None


class QueryResponse(BaseModel):
    answer: str
    clips: list[str]
    confidence: float


@router.post("", response_model=QueryResponse)
async def query(req: QueryRequest, user: CurrentUser) -> QueryResponse:
    if not req.question.strip():
        raise HTTPException(status_code=422, detail="question cannot be empty")

    payload = {
        "question": req.question,
        "owner_id": user["sub"],
        "conversation_history": req.conversation_history,
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
            status_code=exc.response.status_code,
            detail=exc.response.text,
        ) from exc

    data = resp.json()
    return QueryResponse(
        answer=data["answer"],
        clips=data["clips"],
        confidence=data["confidence"],
    )
