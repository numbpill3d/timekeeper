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
from omniscient_shared.time import LOCAL_TIMEZONE

try:
    from .db import get_pool
    from .llm import nl_to_sql, synthesize_response
    from .rag import retrieve_context
    from .structured_query import build_fallback_query
except ImportError:  # Support the repository's direct-module test harness.
    from db import get_pool
    from llm import nl_to_sql, synthesize_response
    from rag import retrieve_context
    from structured_query import build_fallback_query

log = logging.getLogger(__name__)

_DB_URL = os.getenv("DATABASE_URL", "")

# Allowlist: only SELECT statements may pass through
_SELECT_RE = re.compile(r"^\s*SELECT\b", re.IGNORECASE)
# Strip markdown fences LLMs sometimes wrap SQL in
_FENCE_RE = re.compile(r"```(?:sql)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)
_TABLE_RE = re.compile(
    r"\b(?:FROM|JOIN)\s+(?:[a-zA-Z_][\w]*\.)?([a-zA-Z_][\w]*)",
    re.IGNORECASE,
)
_UNSAFE_FUNCTION_RE = re.compile(
    r"\b(?:pg_read_file|pg_read_binary_file|pg_ls_dir|pg_stat_file|"
    r"pg_terminate_backend|pg_cancel_backend|pg_reload_conf|set_config|"
    r"current_setting|dblink_connect|dblink_exec|lo_import|lo_export|"
    r"pg_sleep)\s*\(",
    re.IGNORECASE,
)
_ALLOWED_TABLES = {"events", "persons", "tracked_objects", "cameras"}


def _extract_sql(raw: str) -> str:
    m = _FENCE_RE.search(raw)
    return m.group(1).strip() if m else raw.strip()


def _safe_sql(sql: str) -> str:
    if not _SELECT_RE.match(sql):
        raise ValueError(f"non-SELECT statement rejected: {sql[:80]}")
    if ";" in sql or "--" in sql or "/*" in sql or "*/" in sql:
        raise ValueError("multiple statements and SQL comments are not allowed")
    if re.search(
        r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|GRANT|REVOKE|COPY|CREATE|"
        r"INTO|CALL|DO|EXECUTE|LISTEN|NOTIFY|VACUUM|ANALYZE)\b",
        sql,
        re.IGNORECASE,
    ):
        raise ValueError("unsafe SQL keyword rejected")
    if _UNSAFE_FUNCTION_RE.search(sql):
        raise ValueError("unsafe SQL function rejected")
    if not re.search(r"\bFROM\s+(?:[a-zA-Z_][\w]*\.)?events\b", sql, re.IGNORECASE):
        raise ValueError("query must read from the events table")
    if re.search(r"\b(UNION|INTERSECT|EXCEPT|WITH)\b", sql, re.IGNORECASE):
        raise ValueError("set operations and CTEs are not allowed")
    tables = {match.group(1).lower() for match in _TABLE_RE.finditer(sql)}
    unexpected = tables - _ALLOWED_TABLES
    if unexpected:
        raise ValueError(f"query references disallowed tables: {sorted(unexpected)}")
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
    try:
        raw_sql = await nl_to_sql(question, llm_context)
        fallback_params: list[object] = []
    except RuntimeError as exc:
        log.warning("LLM SQL planner unavailable; using structured fallback: %s", exc)
        raw_sql, fallback_params = build_fallback_query(question)
    sql = _safe_sql(_extract_sql(raw_sql))

    # Scope all queries to the requesting owner's cameras; owner_id passed
    # as a parameter to avoid SQL injection.
    sql = _inject_owner_scope(sql)

    rows = await _execute(sql, owner_id, fallback_params)
    answer_text = await synthesize_response(question, rows, llm_context)

    clips = [r["clip_path"] for r in rows if r.get("clip_path")]
    confidences = [r["confidence"] for r in rows if r.get("confidence")]
    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

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
    match = re.search(
        r"\bFROM\s+(?:[a-zA-Z_][\w]*\.)?events(?:\s+(?:AS\s+)?([a-zA-Z_]\w*))?",
        sql,
        re.IGNORECASE,
    )
    reserved = {"WHERE", "JOIN", "LEFT", "RIGHT", "INNER", "OUTER", "ORDER", "GROUP", "LIMIT"}
    candidate = match.group(1) if match else None
    alias = candidate if candidate and candidate.upper() not in reserved else "events"
    scope = f"{alias}.camera_id IN (SELECT id FROM cameras WHERE owner_id = $1::uuid)"
    statement = sql.rstrip(";").rstrip()
    # Filters must be added before ORDER BY/GROUP BY/LIMIT/OFFSET. Appending
    # after LIMIT produces invalid SQL and can make the caller mistake an
    # execution failure for a legitimate empty result set.
    clause = re.search(r"\b(?:ORDER\s+BY|GROUP\s+BY|LIMIT|OFFSET)\b", statement, re.IGNORECASE)
    split_at = clause.start() if clause else len(statement)
    head = statement[:split_at].rstrip()
    tail = statement[split_at:].lstrip()
    predicate = f" AND {scope}" if re.search(r"\bWHERE\b", head, re.IGNORECASE) else f" WHERE {scope}"
    return f"{head}{predicate}{(' ' + tail) if tail else ''}"


async def _execute(
    sql: str, owner_id: str, extra_params: list[object] | None = None
) -> list[dict]:
    pool = get_pool()
    async with pool.acquire() as conn:
        try:
            # Generated SQL is untrusted model output. A read-only transaction
            # blocks mutation even if validation misses a dialect edge case;
            # timeout and row caps keep one query from monopolizing the service.
            bounded_sql = f"SELECT * FROM ({sql}) AS timekeeper_result LIMIT 50"
            async with conn.transaction():
                await conn.execute("SET TRANSACTION READ ONLY")
                await conn.execute(
                    "SELECT set_config('TimeZone', $1, true)",
                    LOCAL_TIMEZONE.key,
                )
                await conn.execute("SET LOCAL statement_timeout = '5000ms'")
                rows = await conn.fetch(
                    bounded_sql, owner_id, *(extra_params or [])
                )
            return [dict(r) for r in rows]
        except asyncpg.PostgresError as exc:
            log.error("query failed: %s | sql: %s", exc, sql)
            raise RuntimeError("query execution unavailable") from exc
