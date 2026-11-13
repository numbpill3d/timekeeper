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

# Allowlist: only SELECT statements may pass through
_SELECT_RE = re.compile(r"^\s*SELECT\b", re.IGNORECASE)
# Strip markdown fences LLMs sometimes wrap SQL in
_FENCE_RE = re.compile(r"```(?:sql)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)
_TABLE_RE = re.compile(
    r"\b(?:FROM|JOIN)\s+(?:[a-zA-Z_][\w]*\.)?([a-zA-Z_][\w]*)",
    re.IGNORECASE,
)
_RELATION_RE = re.compile(
    r"\b(?:FROM|JOIN)\s+(?:[a-zA-Z_][\w]*\.)?"
    r"(?P<table>[a-zA-Z_][\w]*)"
    r"(?:\s+(?:AS\s+)?(?P<alias>[a-zA-Z_][\w]*))?",
    re.IGNORECASE,
)
_JOIN_RE = re.compile(
    r"\bJOIN\s+(?:[a-zA-Z_][\w]*\.)?(?P<table>[a-zA-Z_][\w]*)"
    r"(?:\s+(?:AS\s+)?(?P<alias>[a-zA-Z_][\w]*))?\s+ON\s+"
    r"(?P<condition>.*?)(?=\b(?:JOIN|WHERE|GROUP\s+BY|ORDER\s+BY|"
    r"HAVING|LIMIT|OFFSET)\b|$)",
    re.IGNORECASE | re.DOTALL,
)
_FROM_SECTION_RE = re.compile(
    r"\bFROM\b(?P<section>.*?)(?=\bWHERE\b|\bGROUP\s+BY\b|"
    r"\bORDER\s+BY\b|\bHAVING\b|\bLIMIT\b|\bOFFSET\b|$)",
    re.IGNORECASE | re.DOTALL,
)
_UNSAFE_FUNCTION_RE = re.compile(
    r"\b(?:pg_read_file|pg_read_binary_file|pg_ls_dir|pg_stat_file|"
    r"pg_terminate_backend|pg_cancel_backend|pg_reload_conf|set_config|"
    r"current_setting|dblink_connect|dblink_exec|lo_import|lo_export|"
    r"pg_sleep)\s*\(",
    re.IGNORECASE,
)
_ALLOWED_TABLES = {"events", "persons", "tracked_objects", "cameras"}
_SQL_RESERVED = {
    "WHERE", "JOIN", "LEFT", "RIGHT", "INNER", "OUTER", "FULL", "CROSS",
    "ON", "ORDER", "GROUP", "HAVING", "LIMIT", "OFFSET",
}


def _relations(sql: str) -> list[tuple[str, str]]:
    """Return (table, alias) pairs for the flat query grammar."""
    relations = []
    for match in _RELATION_RE.finditer(sql):
        table = match.group("table").lower()
        alias = (match.group("alias") or table).lower()
        if alias.upper() in _SQL_RESERVED:
            alias = table
        relations.append((table, alias))
    return relations


def _extract_sql(raw: str) -> str:
    m = _FENCE_RE.search(raw)
    return m.group(1).strip() if m else raw.strip()


def _safe_sql(sql: str) -> str:
    if not _SELECT_RE.match(sql):
        raise ValueError(f"non-SELECT statement rejected: {sql[:80]}")
    if len(re.findall(r"\bSELECT\b", sql, re.IGNORECASE)) != 1:
        raise ValueError("nested SELECT queries are not allowed")
    if ";" in sql or "--" in sql or "/*" in sql or "*/" in sql:
        raise ValueError("multiple statements and SQL comments are not allowed")
    if re.search(
        r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|GRANT|REVOKE|COPY|CREATE|"
        r"INTO|CALL|DO|EXECUTE|LISTEN|NOTIFY|VACUUM|ANALYZE|LATERAL)\b",
        sql,
        re.IGNORECASE,
    ):
        raise ValueError("unsafe SQL keyword rejected")
    if _UNSAFE_FUNCTION_RE.search(sql):
        raise ValueError("unsafe SQL function rejected")
    if not re.search(r"\bFROM\s+(?:[a-zA-Z_][\w]*\.)?events\b", sql, re.IGNORECASE):
        raise ValueError("query must read from the events table")
    from_section = _FROM_SECTION_RE.search(sql)
    if from_section and "," in from_section.group("section"):
        raise ValueError("comma-separated FROM relations are not allowed")
    if re.search(r"\b(UNION|INTERSECT|EXCEPT|WITH)\b", sql, re.IGNORECASE):
        raise ValueError("set operations and CTEs are not allowed")
    tables = {match.group(1).lower() for match in _TABLE_RE.finditer(sql)}
    unexpected = tables - _ALLOWED_TABLES
    if unexpected:
        raise ValueError(f"query references disallowed tables: {sorted(unexpected)}")
    relations = _relations(sql)
    event_relations = [alias for table, alias in relations if table == "events"]
    if len(event_relations) != 1:
        raise ValueError("query must contain exactly one events relation")
    event_alias = event_relations[0]
    join_keys = {
        "persons": "person_id",
        "tracked_objects": "object_id",
        "cameras": "camera_id",
    }
    for match in _JOIN_RE.finditer(sql):
        table = match.group("table").lower()
        alias = (match.group("alias") or table).lower()
        if alias.upper() in _SQL_RESERVED:
            alias = table
        key = join_keys.get(table)
        if key and (
            not re.search(rf"\b{re.escape(alias)}\.id\b", match.group("condition"), re.IGNORECASE)
            or not re.search(
                rf"\b{re.escape(event_alias)}\.{key}\b",
                match.group("condition"),
                re.IGNORECASE,
            )
        ):
            raise ValueError(f"{table} joins must use events.{key}")
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

    # Retrieved event text is evidence for the final answer, not instructions
    # for the SQL planner. Keeping it out of this prompt prevents stored labels
    # or action text from steering query generation.
    planner_context = history_text
    try:
        raw_sql = await nl_to_sql(question, planner_context)
        fallback_params: list[object] = []
    except RuntimeError as exc:
        log.warning("LLM SQL planner unavailable; using structured fallback: %s", exc)
        raw_sql, fallback_params = build_fallback_query(question)
    try:
        sql = _safe_sql(_extract_sql(raw_sql))
    except ValueError as exc:
        # A reachable model can still return malformed or unsafe SQL. Treat
        # that the same as planner unavailability; the local fallback is
        # bounded and remains subject to the same validator.
        log.warning(
            "LLM SQL planner output rejected; using structured fallback: %s",
            type(exc).__name__,
        )
        raw_sql, fallback_params = build_fallback_query(question)
        sql = _safe_sql(_extract_sql(raw_sql))

    # Scope all queries to the requesting owner's cameras; owner_id passed
    # as a parameter to avoid SQL injection.
    sql = _inject_owner_scope(sql)

    rows = await _execute(sql, owner_id, fallback_params)
    answer_context = "\n".join(filter(None, [history_text, rag_context]))
    answer_text = await synthesize_response(question, rows, answer_context)

    clips = [r["clip_path"] for r in rows if r.get("clip_path")]
    # Zero is a valid confidence value and must not disappear from the
    # aggregate merely because it is falsey.
    confidences = [
        r["confidence"] for r in rows if r.get("confidence") is not None
    ]
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
    reserved = _SQL_RESERVED
    candidate = match.group(1) if match else None
    alias = candidate if candidate and candidate.upper() not in reserved else "events"
    scopes = [
        f"{alias}.camera_id IN (SELECT id FROM cameras WHERE owner_id = $1::uuid)"
    ]
    for table, relation_alias in _relations(sql):
        if table in {"persons", "tracked_objects", "cameras"}:
            scopes.append(f"{relation_alias}.owner_id = $1::uuid")
    statement = sql.rstrip(";").rstrip()
    # Filters must be added before ORDER BY/GROUP BY/LIMIT/OFFSET. Appending
    # after LIMIT produces invalid SQL and can make the caller mistake an
    # execution failure for a legitimate empty result set.
    clause = re.search(r"\b(?:ORDER\s+BY|GROUP\s+BY|LIMIT|OFFSET)\b", statement, re.IGNORECASE)
    split_at = clause.start() if clause else len(statement)
    head = statement[:split_at].rstrip()
    tail = statement[split_at:].lstrip()
    scope = " AND ".join(scopes)
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
