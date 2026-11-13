"""Small, parameterized fallback query planner for common event questions.

This is intentionally conservative. It only extracts terms that can be
matched against recorded person/object labels and relative time windows; it
never invents an identity or an action. The LLM remains the richer planner,
but this keeps the local assistant useful when Ollama is starting or absent.
"""

from __future__ import annotations

import re
from datetime import datetime, time, timedelta

from omniscient_shared.time import local_now

_OBJECT_TERMS = {
    "keys", "key", "wallet", "phone", "bag", "backpack", "package",
    "laptop", "tablet", "glasses", "medication", "toolbox", "bottle", "cup", "book",
    "tool", "scissors",
}
_OBJECT_ALIASES = {"scissors": "tool"}
_STOPWORDS = {
    "who", "what", "where", "when", "did", "does", "the", "my", "me",
    "any", "someone", "somebody", "person", "pick", "picked", "pickup",
    "grab", "grabbed", "take", "took", "move", "moved", "place", "placed",
    "left", "leave", "find", "happen", "happened", "with", "about", "is", "up",
    "item", "object", "thing",
    "are", "was", "were", "to", "from", "between", "and", "through", "there",
    "a", "an", "at", "in", "on", "of", "today",
    "yesterday", "recently", "last", "hours", "hour", "minutes", "minute",
    "this", "morning", "afternoon", "evening", "tonight", "night",
    "am", "pm",
}
_LOCATION_RE = re.compile(
    r"\b(?:in|at|near)\s+(?:(?:the|my|our)\s+)?"
    r"(?P<phrase>[a-z][a-z0-9_-]*(?:\s+[a-z][a-z0-9_-]*){0,3})",
    re.IGNORECASE,
)
_GENERIC_OBJECT_QUESTION_RE = re.compile(
    r"\b(?:what happened to|where (?:is|was|were))\b", re.IGNORECASE
)
_HISTORY_QUESTION_RE = re.compile(
    r"\b(?:what happened to|follow|track|where did .*\bgo|sequence|history)\b",
    re.IGNORECASE,
)
_ACTION_EVENT_TYPES = (
    (re.compile(r"\b(?:pick|picked|pickup|grab|grabbed|take|took)\b", re.IGNORECASE), "object_picked_up"),
    (re.compile(r"\b(?:place|placed|put|set)\b", re.IGNORECASE), "object_placed"),
    (re.compile(r"\b(?:move|moved|carry|carried)\b", re.IGNORECASE), "object_moved"),
    (re.compile(r"\b(?:leave|left|exit|exited)\b", re.IGNORECASE), "person_exited"),
    (re.compile(r"\b(?:enter|entered|arrive|arrived|came)\b", re.IGNORECASE), "person_entered"),
)
_TIME_RANGE_RE = re.compile(
    r"\b(?:between|from)\s+"
    r"(?P<start_hour>\d{1,2})(?::(?P<start_minute>[0-5]\d))?\s*"
    r"(?P<start_ampm>a\.?m\.?|p\.?m\.?)?\s*"
    r"(?:and|to|through|-)\s*"
    r"(?P<end_hour>\d{1,2})(?::(?P<end_minute>[0-5]\d))?\s*"
    r"(?P<end_ampm>a\.?m\.?|p\.?m\.?)?\b",
    re.IGNORECASE,
)


def _terms(question: str) -> list[str]:
    quoted = re.findall(r"[\"']([^\"']+)[\"']", question)
    unquoted = re.sub(r"[\"'][^\"']+[\"']", " ", question.lower())
    words = re.findall(r"[a-z0-9][a-z0-9_-]{1,31}", unquoted)
    candidates = quoted + [
        word for word in words
        if word not in _STOPWORDS and not word.isdigit()
    ]
    return list(dict.fromkeys(term.strip() for term in candidates if term.strip()))


def _location_term(question: str) -> str | None:
    """Extract a short location phrase after a location preposition."""
    match = _LOCATION_RE.search(question.lower())
    if not match:
        return None
    stopwords = _STOPWORDS | {"during", "from", "until", "for"}
    words = []
    for word in match.group("phrase").split():
        if word in stopwords:
            break
        words.append(word)
    return " ".join(words) or None


def _action_event_type(question: str) -> str | None:
    """Constrain explicit action questions without guessing for open-ended ones."""
    for pattern, event_type in _ACTION_EVENT_TYPES:
        if pattern.search(question):
            return event_type
    return None


def _clock_datetime(
    day, hour_text: str, minute_text: str | None, ampm: str | None, tzinfo
) -> datetime | None:
    hour = int(hour_text)
    minute = int(minute_text or 0)
    if ampm:
        if hour < 1 or hour > 12:
            return None
        if ampm.startswith("p") and hour != 12:
            hour += 12
        if ampm.startswith("a") and hour == 12:
            hour = 0
    elif hour > 23:
        return None
    return datetime.combine(day, time(hour, minute), tzinfo=tzinfo)


def _time_predicates(question: str, start_param: int) -> tuple[list[str], list[object]]:
    lowered = question.lower()
    now = local_now()
    match = re.search(r"last\s+(\d+)\s*(hour|hours|minute|minutes)", lowered)
    if match:
        amount = int(match.group(1))
        delta = timedelta(**({"hours": amount} if match.group(2).startswith("hour") else {"minutes": amount}))
        return [f"e.timestamp >= ${start_param}"], [now - delta]

    day = (now - timedelta(days=1)).date() if "yesterday" in lowered else now.date()
    time_range = _TIME_RANGE_RE.search(lowered)
    if time_range:
        start_ampm = time_range.group("start_ampm") or time_range.group("end_ampm")
        end_ampm = time_range.group("end_ampm") or start_ampm
        start = _clock_datetime(
            day,
            time_range.group("start_hour"),
            time_range.group("start_minute"),
            start_ampm,
            now.tzinfo,
        )
        end = _clock_datetime(
            day,
            time_range.group("end_hour"),
            time_range.group("end_minute"),
            end_ampm,
            now.tzinfo,
        )
        if start is not None and end is not None:
            if end <= start:
                end += timedelta(days=1)
            return [
                f"e.timestamp >= ${start_param}",
                f"e.timestamp < ${start_param + 1}",
            ], [start, end]

    clock = re.search(
        r"\b(?:at\s+)?(?P<hour>\d{1,2})(?::(?P<minute>[0-5]\d))?\s*"
        r"(?P<ampm>a\.?m\.?|p\.?m\.?)\b",
        lowered,
    )
    if clock:
        hour = int(clock.group("hour"))
        minute = int(clock.group("minute") or 0)
        if hour < 1 or hour > 12:
            return [], []
        if clock.group("ampm").startswith("p") and hour != 12:
            hour += 12
        if clock.group("ampm").startswith("a") and hour == 12:
            hour = 0
        start = datetime.combine(day, time(hour, minute), tzinfo=now.tzinfo)
        return [
            f"e.timestamp >= ${start_param}",
            f"e.timestamp < ${start_param + 1}",
        ], [start, start + timedelta(minutes=1)]

    clock_24 = re.search(
        r"\b(?:at\s+)?(?P<hour>[01]?\d|2[0-3]):(?P<minute>[0-5]\d)\b",
        lowered,
    )
    if clock_24:
        start = datetime.combine(
            day,
            time(int(clock_24.group("hour")), int(clock_24.group("minute"))),
            tzinfo=now.tzinfo,
        )
        return [
            f"e.timestamp >= ${start_param}",
            f"e.timestamp < ${start_param + 1}",
        ], [start, start + timedelta(minutes=1)]

    day_parts = (
        ("morning", time(0, 0), time(12, 0)),
        ("afternoon", time(12, 0), time(18, 0)),
        ("evening", time(18, 0), time(23, 59, 59, 999999)),
        ("tonight", time(18, 0), time(23, 59, 59, 999999)),
        ("night", time(18, 0), time(23, 59, 59, 999999)),
    )
    for word, start_time, end_time in day_parts:
        if word in lowered:
            start = datetime.combine(day, start_time, tzinfo=now.tzinfo)
            end = datetime.combine(day, end_time, tzinfo=now.tzinfo)
            return [f"e.timestamp >= ${start_param}", f"e.timestamp <= ${start_param + 1}"], [start, end]

    start = datetime.combine(day, datetime.min.time(), tzinfo=now.tzinfo)
    if "yesterday" in lowered:
        return [f"e.timestamp >= ${start_param}", f"e.timestamp < ${start_param + 1}"], [start, start + timedelta(days=1)]
    return [f"e.timestamp >= ${start_param}"], [start]


def build_fallback_query(question: str) -> tuple[str, list[object]]:
    """Return ``(SELECT, parameters_without_owner)`` for a safe event search."""
    terms = _terms(question)
    location = _location_term(question)
    location_tokens = set(location.split()) if location else set()
    generic_object_question = bool(
        _GENERIC_OBJECT_QUESTION_RE.search(question)
    )
    object_sources = [
        term
        for term in terms
        if term.rstrip("s") in {t.rstrip("s") for t in _OBJECT_TERMS}
    ]
    object_terms = (
        [" ".join(term for term in terms if term not in location_tokens)]
        if generic_object_question and terms and not (
            len(terms) == 1 and terms[0] in object_sources
        )
        else [_OBJECT_ALIASES.get(term, term) for term in object_sources]
    )
    person_terms = [] if generic_object_question else [
        term for term in terms
        if term not in object_sources and term not in location_tokens
    ]

    # The query router injects the owner scope centrally after validating this
    # single-level SELECT. Keeping it out here prevents a second, unscoped
    # subquery from becoming part of the trusted fallback contract.
    clauses: list[str] = []
    params: list[object] = []
    next_param = 2

    if object_terms:
        clauses.append(
            f"(o.category ILIKE ${next_param} OR o.label ILIKE ${next_param} "
            f"OR e.action_label ILIKE ${next_param})"
        )
        params.append(f"%{object_terms[0]}%")
        next_param += 1
    if person_terms:
        clauses.append(f"p.label ILIKE ${next_param}")
        params.append(f"%{person_terms[0]}%")
        next_param += 1
    if location:
        clauses.append(f"e.location_label ILIKE ${next_param}")
        params.append(f"%{location}%")
        next_param += 1

    time_clauses, time_params = _time_predicates(question, next_param)
    clauses.extend(time_clauses)
    params.extend(time_params)
    action_event_type = _action_event_type(question)
    if action_event_type:
        action_param = next_param + len(time_params)
        clauses.append(f"e.event_type = ${action_param}")
        params.append(action_event_type)

    ordering = "ASC" if _HISTORY_QUESTION_RE.search(question) else "DESC"
    sql = f"""
        SELECT e.id AS event_id, e.timestamp, e.event_type, e.action_label, e.location_label,
               c.name AS camera_name,
               e.confidence, e.clip_path,
               p.label AS person_label,
               o.label AS object_label,
               o.category AS object_category
        FROM events e
        JOIN cameras c ON e.camera_id = c.id
        LEFT JOIN persons p ON e.person_id = p.id
        LEFT JOIN tracked_objects o ON e.object_id = o.id
        WHERE {' AND '.join(clauses)}
        ORDER BY e.timestamp {ordering}
        LIMIT 50
    """
    return sql, params
