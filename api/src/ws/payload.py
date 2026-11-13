"""Validated, public event payloads for live clients."""

from __future__ import annotations

from omniscient_shared.models.event import Event
from pydantic import ValidationError

from ..media import safe_signed_clip_url


def public_event_payload(
    value: object,
    *,
    person_label: str | None = None,
    object_label: str | None = None,
) -> dict | None:
    """Validate Kafka data and expose only the REST-shaped public fields."""
    try:
        event = Event.model_validate(value)
    except (TypeError, ValueError, ValidationError):
        return None
    clip_path = safe_signed_clip_url(event.clip_path)
    serialized = event.model_dump(mode="json")
    return {
        "id": serialized["id"],
        "camera_id": serialized["camera_id"],
        "event_type": serialized["event_type"],
        "timestamp": serialized["timestamp"],
        "action_label": serialized["action_label"],
        "location_label": serialized["location_label"],
        "confidence": serialized["confidence"],
        "clip_path": clip_path,
        "person_label": person_label,
        "object_label": object_label,
    }
