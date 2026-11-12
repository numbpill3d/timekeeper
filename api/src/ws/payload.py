"""Validated, public event payloads for live clients."""

from __future__ import annotations

from omniscient_shared.models.event import Event
from pydantic import ValidationError

from ..media import signed_clip_url


def public_event_payload(value: object) -> dict | None:
    """Validate Kafka data and expose only the REST-shaped public fields."""
    try:
        event = Event.model_validate(value)
    except (TypeError, ValueError, ValidationError):
        return None
    try:
        clip_path = signed_clip_url(event.clip_path)
    except Exception:  # noqa: BLE001 - storage SDK failures must not kill the stream
        clip_path = None
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
        "person_label": None,
        "object_label": None,
    }
