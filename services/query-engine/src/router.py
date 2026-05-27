"""
NL query router: question -> SQL -> rows -> natural language answer.

Pipeline:
  1. Embed the question for RAG retrieval (semantic search over past events)
  2. Ask LLM to generate a SQL query from the question + schema
  3. Validate + execute the SQL against TimescaleDB
  4. Synthesize a natural language response from the rows
"""

from __future__ import annotations

import logging
import os
import re

import asyncpg

from .db import get_pool
from .llm import nl_to_sql, synthesize_response
from .rag import retrieve_context

log = logging.getLogger(__name__)

_DB_URL = os.getenv("DATABASE_URL", "")

# Allowlist: only SELECT statements may pass through
_SELECT_RE = re.compile(r"^\s*SELECT\b", re.IGNORECASE)
# Strip markdown fences LLMs sometimes wrap SQL in
_FENCE_RE = re.compile(r"```(?:sql)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


def _extract_sql(raw: str) -> str:
    m = _FENCE_RE.search(raw)
    return m.group(1).strip() if m else raw.strip()


def _safe_sql(sql: str) -> str:
    if not _SELECT_RE.match(sql):
        raise ValueError(f"non-SELECT statement rejected: {sql[:80]}")
    return sql


async def answer(
    question: str,
    owner_id: str,
    conversation_history: list[dict] | None = None,
) -> dict:
    """End-to-end query: question -> answer + supporting data.

    Returns:
      {
        "answer": str,           # natural language response
        "sql": str,              # the generated query (for debugging)
        "rows": list[dict],      # raw result rows
        "clips": list[str],      # clip_paths from matching events
        "confidence": float,     # average detection confidence
      }
    """
    history_text = _format_history(conversation_history or [])

    # RAG: retrieve semantically relevant past events as extra context
    rag_context = await retrieve_context(question, owner_id)

    llm_context = "\n".join(filter(None, [history_text, rag_context]))
    raw_sql = await nl_to_sql(question, llm_context)
    sql = _safe_sql(_extract_sql(raw_sql))

    # Scope all queries to the requesting owner's cameras; owner_id passed
    # as a parameter to avoid SQL injection.
    sql = _inject_owner_scope(sql)

    rows = await _execute(sql, owner_id)
    answer_text = await synthesize_response(question, rows, llm_context)

    clips = [r["clip_path"] for r in rows if r.get("clip_path")]
    confidences = [r["confidence"] for r in rows if r.get("confidence")]
    avg_conf = sum(confidences) / len(confidences) if confidences else 1.0

    return {
        "answer": answer_text,
        "sql": sql,
        "rows": rows,
        "clips": clips,
        "confidence": avg_conf,
    }


def _format_history(history: list[dict]) -> str:
    if not history:
        return ""
    lines = []
    for turn in history[-6:]:  # last 3 exchanges
        role = turn.get("role", "user")
        lines.append(f"{role}: {turn.get('content', '')}")
    return "\n".join(lines)


def _inject_owner_scope(sql: str) -> str:
    """Append a camera ownership filter using a $1 parameter placeholder."""
    scope = "events.camera_id IN (SELECT id FROM cameras WHERE owner_id = $1::uuid)"
    if re.search(r"\bWHERE\b", sql, re.IGNORECASE):
        return sql.rstrip(";") + f" AND {scope}"
    return sql.rstrip(";") + f" WHERE {scope}"


async def _execute(sql: str, owner_id: str) -> list[dict]:
    pool = get_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(sql, owner_id)
            return [dict(r) for r in rows]
        except asyncpg.PostgresError as exc:
            log.error("query failed: %s | sql: %s", exc, sql)
            return []
