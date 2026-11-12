"""
Query Engine — FastAPI service, port 8001.

Endpoints:
  POST /query          NL question -> answer + clips + confidence
  POST /embed          Embed text (used internally by event-processor)
  GET  /health
"""

from __future__ import annotations

import logging
import math
from contextlib import asynccontextmanager
from typing import Literal
from uuid import UUID

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator

try:
    from .db import close_pool, get_pool, init_pool
    from .rag import embed_text
    from .router import answer
except ImportError:  # Support direct-module imports used by local tests.
    from db import close_pool, get_pool, init_pool
    from rag import embed_text
    from router import answer

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    yield
    await close_pool()


app = FastAPI(
    title="Omniscient Query Engine",
    version="0.1.0",
    lifespan=lifespan,
)


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
    question: str = Field(min_length=1, max_length=1000)
    owner_id: UUID
    conversation_history: list[ConversationTurn] | None = Field(
        default=None, max_length=6
    )

    @field_validator("question")
    @classmethod
    def _strip_question(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("question cannot be empty")
        return value


class QueryResponse(BaseModel):
    answer: str = Field(min_length=1, max_length=10000)
    sql: str
    clips: list[str]
    confidence: float = Field(ge=0.0, le=1.0)


class EmbedRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)

    @field_validator("text")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("text cannot be empty")
        return value


class EmbedResponse(BaseModel):
    # all-MiniLM-L6-v2 produces the 384 dimensions used by the pgvector
    # column; accepting another size only defers failure to event persistence.
    embedding: list[float] = Field(min_length=384, max_length=384)

    @field_validator("embedding")
    @classmethod
    def _finite_values(cls, value: list[float]) -> list[float]:
        if not all(math.isfinite(item) for item in value):
            raise ValueError("embedding values must be finite")
        return value


@app.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest) -> QueryResponse:
    if not req.question.strip():
        raise HTTPException(status_code=422, detail="question cannot be empty")

    try:
        result = await answer(
            question=req.question,
            owner_id=str(req.owner_id),
            conversation_history=[
                turn.model_dump() for turn in (req.conversation_history or [])
            ],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return QueryResponse(
        answer=result["answer"],
        sql=result["sql"],
        clips=result["clips"],
        confidence=result["confidence"],
    )


@app.post("/embed", response_model=EmbedResponse)
async def embed(req: EmbedRequest) -> EmbedResponse:
    try:
        vec = embed_text(req.text)
    except Exception as exc:
        log.exception("embedding failed")
        raise HTTPException(status_code=503, detail="embedding service unavailable") from exc
    return EmbedResponse(embedding=vec)


@app.get("/health")
async def health() -> dict:
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
    except Exception as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    return {"status": "ok", "database": "ok"}
