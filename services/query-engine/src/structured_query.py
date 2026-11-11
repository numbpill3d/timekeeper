"""Small, parameterized fallback query planner for common event questions.

This is intentionally conservative. It only extracts terms that can be
matched against recorded person/object labels and relative time windows; it
never invents an identity or an action. The LLM remains the richer planner,
but this keeps the local assistant useful when Ollama is starting or absent.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

_OBJECT_TERMS = {
    "keys", "key", "wallet", "phone", "bag", "backpack", "package",
    "laptop", "tablet", "glasses", "medication", "bottle", "cup", "book",
}
_STOPWORDS = {
    "who", "what", "where", "when", "did", "does", "the", "my", "me",
    "any", "someone", "somebody", "person", "pick", "picked", "pickup",
    "grab", "grabbed", "take", "took", "move", "moved", "place", "placed",
    "left", "leave", "find", "happen", "happened", "with", "about", "is", "up",
    "are", "was", "were", "to", "a", "an", "at", "in", "on", "of", "today",
    "yesterday", "recently", "last", "hours", "hour", "minutes", "minute",
}


def _terms(question: str) -> list[str]:
    quoted = re.findall(r"[\"']([^\"']+)[\"']", question)
    words = re.findall(r"[a-z0-9][a-z0-9_-]{1,31}", question.lower())
    candidates = quoted + [word for word in words if word not in _STOPWORDS]
    return list(dict.fromkeys(term.strip() for term in candidates if term.strip()))


def _time_predicates(question: str, start_param: int) -> tuple[list[str], list[object]]:
    lowered = question.lower()
    now = datetime.now(tz=timezone.utc)
    if "yesterday" in lowered:
        start = datetime.combine(
            (now - timedelta(days=1)).date(), datetime.min.time(), tzinfo=timezone.utc
        )
        end = start + timedelta(days=1)
        return [f"e.timestamp >= ${start_param}", f"e.timestamp < ${start_param + 1}"], [start, end]
    match = re.search(r"last\s+(\d+)\s*(hour|hours|minute|minutes)", lowered)
    if match:
        amount = int(match.group(1))
        delta = timedelta(**({"hours": amount} if match.group(2).startswith("hour") else {"minutes": amount}))
        return [f"e.timestamp >= ${start_param}"], [now - delta]
    if "today" in lowered or not any(word in lowered for word in ("yesterday", "last")):
        start = datetime.combine(now.date(), datetime.min.time(), tzinfo=timezone.utc)
        return [f"e.timestamp >= ${start_param}"], [start]
    return [], []


def build_fallback_query(question: str) -> tuple[str, list[object]]:
    """Return ``(SELECT, parameters_without_owner)`` for a safe event search."""
    terms = _terms(question)
    object_terms = [term for term in terms if term.rstrip("s") in {t.rstrip("s") for t in _OBJECT_TERMS}]
    person_terms = [term for term in terms if term not in object_terms]

    clauses = [
        "e.camera_id IN (SELECT id FROM cameras WHERE owner_id = $1::uuid)",
    ]
    params: list[object] = []
    next_param = 2

    if object_terms:
        clauses.append(
            "(o.category ILIKE $%d OR o.label ILIKE $%d OR e.action_label ILIKE $%d)"
            % (next_param, next_param, next_param)
        )
        params.append(f"%{object_terms[0]}%")
        next_param += 1
    if person_terms:
        clauses.append("p.label ILIKE $%d" % next_param)
        params.append(f"%{person_terms[0]}%")
        next_param += 1

    time_clauses, time_params = _time_predicates(question, next_param)
    clauses.extend(time_clauses)
    params.extend(time_params)

    sql = """
        SELECT e.timestamp, e.event_type, e.action_label, e.location_label,
               e.confidence, e.clip_path,
               p.label AS person_label,
               o.label AS object_label,
               o.category AS object_category
        FROM events e
        LEFT JOIN persons p ON e.person_id = p.id
        LEFT JOIN tracked_objects o ON e.object_id = o.id
        WHERE %s
        ORDER BY e.timestamp DESC
        LIMIT 50
    """ % " AND ".join(clauses)
    return sql, params
