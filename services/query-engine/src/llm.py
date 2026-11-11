"""
LLM client with Ollama-first, OpenAI fallback.

Used for two tasks:
  1. Text-to-SQL: translate a natural language question into a SQL query
     against the events/persons/tracked_objects schema.
  2. Response synthesis: turn raw SQL results into a human-readable answer.
"""

from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)

_OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
_OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral")
_OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")

_SQL_SYSTEM = """
You are a SQL expert for a home surveillance database.
Schema:

  events(id, camera_id, event_type, timestamp, person_id, object_id,
         location_label, action_label, confidence, metadata, clip_path)
  persons(id, label, is_known, last_seen_at)
  tracked_objects(id, category, label, last_camera_id, last_seen_at)
  cameras(id, name, location_label)

Rules:
- Always return a single valid PostgreSQL SELECT statement, no explanation.
- Use timestamp >= NOW() - INTERVAL '...' for relative time filters.
- Join persons ON events.person_id = persons.id when the query mentions names.
- Join tracked_objects ON events.object_id = tracked_objects.id for objects.
- When returning event rows, select timestamp, action_label, location_label,
  confidence, clip_path, persons.label AS person_label, and
  tracked_objects.label/category AS object_label/object_category when useful.
- For object/person questions, always include those person and object fields
  in the SELECT so the answer can name the evidence-bearing entities.
- Limit results to 50 unless the user asks for more.
- Never produce INSERT, UPDATE, DELETE, or DDL statements.
""".strip()

_SYNTH_SYSTEM = """
You are Omniscient Home, an AI home intelligence assistant.
You answer questions about what happened in the home using structured event data.

Rules:
- Be concise and direct. Lead with the answer.
- Use natural language, not JSON or SQL.
- Include timestamps in human-readable format (e.g. "4:21 PM today").
- If confidence < 0.8, qualify with "I think" or "probably".
- If no results, say so clearly and suggest the user check the camera feed.
- Never hallucinate events not present in the data.
- Treat every row as evidence, not as a guess. If the data does not establish
  who, what, or when, say that it is unknown.
""".strip()


async def _ollama_complete(system: str, user: str) -> str:
    import ollama

    client = ollama.AsyncClient(host=_OLLAMA_URL)
    resp = await client.chat(
        model=_OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return resp["message"]["content"].strip()


async def _openai_complete(system: str, user: str) -> str:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=_OPENAI_KEY)
    resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.0,
    )
    return resp.choices[0].message.content.strip()


async def _complete(system: str, user: str) -> str:
    try:
        return await _ollama_complete(system, user)
    except Exception as exc:
        if not _OPENAI_KEY:
            raise RuntimeError(
                "Ollama unavailable and OPENAI_API_KEY not set"
            ) from exc
        log.warning("ollama failed (%s), falling back to openai", exc)
        try:
            return await _openai_complete(system, user)
        except Exception as openai_exc:
            raise RuntimeError(
                "Ollama and OpenAI completions are unavailable"
            ) from openai_exc


async def nl_to_sql(question: str, context: str = "") -> str:
    """Translate a natural language question to a SQL SELECT statement."""
    prompt = question
    if context:
        prompt = f"Context from conversation:\n{context}\n\nQuestion: {question}"
    return await _complete(_SQL_SYSTEM, prompt)


async def synthesize_response(
    question: str,
    rows: list[dict],
    context: str = "",
) -> str:
    """Turn SQL result rows into a natural language answer."""
    if not rows:
        return "I couldn't find a matching recorded event in the selected camera history."
    rows_text = "\n".join(str(r) for r in rows[:20])
    prompt = (
        f"User asked: {question}\n\n"
        f"Event data:\n{rows_text}"
    )
    if context:
        prompt = f"Conversation context:\n{context}\n\n{prompt}"
    try:
        return await _complete(_SYNTH_SYSTEM, prompt)
    except RuntimeError as exc:
        log.warning("LLM synthesis unavailable; using evidence formatter: %s", exc)
        return _format_evidence_response(rows)


def _format_evidence_response(rows: list[dict]) -> str:
    """Format recorded rows without adding facts not present in the database."""
    lines: list[str] = []
    for row in rows[:5]:
        timestamp = row.get("timestamp")
        time_text = timestamp.strftime("%I:%M %p") if timestamp else "an unknown time"
        person = row.get("person_label") or "An unidentified person"
        item = row.get("object_label") or row.get("object_category") or "the recorded item"
        action = str(row.get("event_type") or row.get("action_label") or "activity")
        location = row.get("location_label")
        where = f" at {location}" if location else ""

        if action == "object_picked_up":
            lines.append(f"At {time_text}, {person} picked up {item}{where}.")
        elif action == "object_moved":
            lines.append(f"At {time_text}, {person} moved {item}{where}.")
        elif action == "object_placed":
            lines.append(f"At {time_text}, {person} was associated with {item}{where}.")
        else:
            label = row.get("action_label") or action.replace("_", " ")
            lines.append(f"At {time_text}, the system recorded {label}{where}.")

    return " ".join(lines)
