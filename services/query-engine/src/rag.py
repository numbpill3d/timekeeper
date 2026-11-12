"""
RAG (Retrieval-Augmented Generation) pipeline.

Embeds incoming questions with sentence-transformers, runs a pgvector
cosine similarity search over the events.embedding column, and returns
the top-k most semantically relevant past events as plain-text context
for the LLM prompt.

Events get their embeddings written by the event-processor service when
they are first persisted (using the same model here).
"""

from __future__ import annotations

import logging
import os

import asyncpg
from omniscient_shared.time import to_local

try:
    from .db import get_pool
except ImportError:  # Support direct-module imports used by local tests.
    from db import get_pool

log = logging.getLogger(__name__)

_DB_URL = os.getenv("DATABASE_URL", "")
_TOP_K = 8
_MODEL_NAME = "all-MiniLM-L6-v2"  # 384-dim, fast, fits on CPU

_embedder = None


def _get_embedder():
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer

        _embedder = SentenceTransformer(_MODEL_NAME)
    return _embedder


def embed_text(text: str) -> list[float]:
    model = _get_embedder()
    vec = model.encode(text, normalize_embeddings=True)
    return vec.tolist()


async def retrieve_context(question: str, owner_id: str) -> str:
    """Return a text block of the k most relevant past events for `question`."""
    try:
        vec = embed_text(question)
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        log.warning("embedding failed: %s", exc)
        return ""

    vec_literal = "[" + ",".join(f"{v:.6f}" for v in vec) + "]"

    sql = """
        SELECT e.action_label, e.timestamp, e.location_label,
               e.confidence, e.event_type,
               p.label AS person_label,
               o.label AS object_label,
               o.category AS object_category
        FROM events e
        LEFT JOIN persons p ON e.person_id = p.id
        LEFT JOIN tracked_objects o ON e.object_id = o.id
        WHERE e.camera_id IN (
            SELECT id FROM cameras WHERE owner_id = $1::uuid
        )
          AND e.embedding IS NOT NULL
        ORDER BY e.embedding <=> $2::vector
        LIMIT $3
    """

    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, owner_id, vec_literal, _TOP_K)
    except (asyncpg.PostgresError, OSError, RuntimeError, ValueError) as exc:
        log.warning("rag retrieval failed: %s", exc)
        return ""

    if not rows:
        return ""

    lines = ["Relevant past events:"]
    for r in rows:
        ts = to_local(r["timestamp"]).strftime("%Y-%m-%d %H:%M") if r["timestamp"] else "?"
        who = r["person_label"] or "unknown person"
        object_name = r["object_label"] or r["object_category"]
        what = r["action_label"] or r["event_type"]
        if object_name and object_name.lower() not in what.lower():
            what = f"{object_name}: {what}"
        where = f" at {r['location_label']}" if r["location_label"] else ""
        lines.append(f"  [{ts}] {who}: {what}{where}")

    return "\n".join(lines)


def embed_event(action_label: str, event_type: str, location: str = "") -> list[float]:
    """Produce an embedding for an event to store in events.embedding."""
    text = f"{event_type}: {action_label}"
    if location:
        text += f" ({location})"
    return embed_text(text)
