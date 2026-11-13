"""
Alert rule evaluation.

Rules are stored as natural language in alert_rules.rule_text and
compiled to a predicate dict on first use (cached in compiled_rule column).

Compiled rule schema:
  {
    "event_types": ["person_entered", ...],   # match any
    "person_labels": ["unknown", ...],         # match any; "unknown" = is_known=False
    "object_categories": ["keys", ...],
    "location_labels": ["backyard", ...],
    "time_after": "HH:MM",                    # 24h, local time
    "time_before": "HH:MM",
    "min_confidence": 0.0
  }
"""

from __future__ import annotations

import json
import logging
import os
import re
from math import isfinite

from omniscient_shared.models.event import Event, EventType
from omniscient_shared.time import to_local

log = logging.getLogger(__name__)

_OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
_OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral")

_TEMPLATES: dict[str, dict] = {
    "unknown person enters": {
        "event_types": [EventType.person_entered.value],
        "person_labels": ["unknown"],
    },
    "intrusion": {
        "event_types": [EventType.intrusion_detected.value],
    },
    "package delivered": {
        "event_types": [EventType.package_delivered.value],
    },
    "after midnight": {
        "time_after": "00:00",
        "time_before": "06:00",
    },
}

_COMPILE_SYSTEM = """
You are an alert rule compiler for a home surveillance system.
Convert a natural language rule into a JSON predicate object.

Predicate schema (only include relevant fields):
{
  "event_types": ["person_entered","person_exited","object_placed",
                  "object_picked_up","object_moved","package_delivered",
                  "intrusion_detected"],
  "person_labels": ["unknown"],
  "object_categories": ["keys","wallet","phone","bag","package"],
  "location_labels": ["front door","backyard","kitchen"],
  "time_after": "HH:MM",
  "time_before": "HH:MM",
  "min_confidence": 0.0
}

Return ONLY valid JSON, no explanation.
""".strip()

_RULE_LIST_FIELDS = {
    "event_types": {event.value for event in EventType},
    "person_labels": None,
    "object_categories": None,
    "location_labels": None,
}
_TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


def normalize_rule(value: object) -> dict:
    """Validate the LLM/database predicate before it reaches evaluation."""
    if not isinstance(value, dict):
        return {}

    normalized: dict = {}
    for field, allowed in _RULE_LIST_FIELDS.items():
        raw = value.get(field)
        if raw is None:
            continue
        if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
            return {}
        items = [item.strip() for item in raw if item.strip()]
        if allowed is not None:
            items = [item for item in items if item in allowed]
            if not items:
                return {}
        normalized[field] = items[:32]

    for field in ("time_after", "time_before"):
        raw = value.get(field)
        if raw is not None:
            if not isinstance(raw, str) or not _TIME_RE.fullmatch(raw):
                return {}
            normalized[field] = raw

    if "min_confidence" in value:
        try:
            confidence = float(value["min_confidence"])
        except (TypeError, ValueError):
            return {}
        if not isfinite(confidence) or not 0.0 <= confidence <= 1.0:
            return {}
        normalized["min_confidence"] = confidence

    return normalized


def compile_rule(rule_text: str) -> dict:
    """Template matching fallback — fast, no LLM required."""
    lower = rule_text.lower()
    for keyword, predicate in _TEMPLATES.items():
        if keyword in lower:
            return predicate
    return {}


async def compile_rule_llm(rule_text: str) -> dict:
    """LLM-based rule compilation. Returns {} on failure."""
    try:
        import ollama

        client = ollama.AsyncClient(host=_OLLAMA_URL)
        resp = await client.chat(
            model=_OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": _COMPILE_SYSTEM},
                {"role": "user", "content": rule_text},
            ],
        )
        raw = resp["message"]["content"].strip()
        if "```" in raw:
            parts = raw.split("```")
            raw = parts[1].lstrip("json").strip() if len(parts) > 1 else raw
        return normalize_rule(json.loads(raw))
    except Exception as exc:  # noqa: BLE001 - optional LLM failures must not block alerts
        log.warning("llm rule compilation failed: %s", exc)
        return {}


def event_matches(
    event: Event,
    rule: dict,
    person_label: str | None,
    person_is_known: bool = True,
    object_category: str | None = None,
) -> bool:
    """Return True if event satisfies the compiled rule predicate."""
    if not rule:
        return True
    if rule.get("_disabled"):
        return False

    types = rule.get("event_types")
    if types and event.event_type.value not in types:
        return False

    p_labels = rule.get("person_labels")
    if p_labels:
        if "unknown" in p_labels:
            # "unknown" means an observed person was resolved and marked
            # unknown; an event with no person association is not evidence of
            # an unknown person and must not trigger this rule.
            if not person_label or person_is_known:
                return False
        else:
            # specific label(s) required
            if not person_label or not any(
                person_label.casefold() == label.casefold() for label in p_labels
            ):
                return False

    obj_cats = rule.get("object_categories")
    if obj_cats and (
        not object_category
        or not any(
            object_category.casefold() == category.casefold()
            for category in obj_cats
        )
    ):
        return False

    locs = rule.get("location_labels")
    if locs and (
        not event.location_label
        or not any(
            event.location_label.casefold() == location.casefold()
            for location in locs
        )
    ):
        return False

    time_after = rule.get("time_after")
    time_before = rule.get("time_before")
    if time_after or time_before:
        t = to_local(event.timestamp)
        hhmm = t.hour * 60 + t.minute
        after_mins = (
            _minutes(time_after) if time_after is not None else None
        )
        before_mins = (
            _minutes(time_before) if time_before is not None else None
        )
        if after_mins is not None and before_mins is not None:
            # A window whose end precedes its start crosses midnight, e.g.
            # 22:00–06:00. Boundaries remain inclusive as they were for the
            # single-sided checks.
            in_window = (
                after_mins <= hhmm <= before_mins
                if after_mins <= before_mins
                else hhmm >= after_mins or hhmm <= before_mins
            )
            if not in_window:
                return False
        elif (
            after_mins is not None and hhmm < after_mins
        ) or (
            before_mins is not None and hhmm > before_mins
        ):
            return False

    min_conf = rule.get("min_confidence", 0.0)
    if event.confidence < min_conf:
        return False

    return event.confidence >= min_conf


def _minutes(value: str) -> int:
    hour, minute = map(int, value.split(":"))
    return hour * 60 + minute
