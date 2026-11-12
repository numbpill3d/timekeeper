"""
Query Engine — FastAPI service, port 8001.

Endpoints:
  POST /query          NL question -> answer + clips + confidence
  POST /embed          Embed text (used internally by event-processor)
  GET  /health
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .db import close_pool, init_pool
from .rag import embed_text
from .router import answer

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
    question: str
    owner_id: str
    conversation_history: list[ConversationTurn] | None = Field(
        default=None, max_length=6
    )


class QueryResponse(BaseModel):
    answer: str
    sql: str
    clips: list[str]
    confidence: float


class EmbedRequest(BaseModel):
    text: str


class EmbedResponse(BaseModel):
    embedding: list[float]


@app.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest) -> QueryResponse:
    if not req.question.strip():
        raise HTTPException(status_code=422, detail="question cannot be empty")

    try:
        result = await answer(
            question=req.question,
            owner_id=req.owner_id,
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
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return EmbedResponse(embedding=vec)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
