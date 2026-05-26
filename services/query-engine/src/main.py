"""
Query Engine — FastAPI service, port 8001.

Endpoints:
  POST /query          NL question -> answer + clips + confidence
  POST /embed          Embed text (used internally by event-processor)
  GET  /health
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .rag import embed_text
from .router import answer

log = logging.getLogger(__name__)

app = FastAPI(title="Omniscient Query Engine", version="0.1.0")


class QueryRequest(BaseModel):
    question: str
    owner_id: str
    conversation_history: list[dict] | None = None


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
            conversation_history=req.conversation_history,
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
