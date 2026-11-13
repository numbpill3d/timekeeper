from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator

from omniscient_shared.time import to_utc


class EventType(str, Enum):
    person_entered = "person_entered"
    person_exited = "person_exited"
    person_detected = "person_detected"
    object_moved = "object_moved"
    object_placed = "object_placed"
    object_picked_up = "object_picked_up"
    door_opened = "door_opened"
    door_closed = "door_closed"
    package_delivered = "package_delivered"
    intrusion_detected = "intrusion_detected"
    unknown_person = "unknown_person"
    fall_detected = "fall_detected"


class Event(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    camera_id: UUID
    event_type: EventType
    timestamp: datetime
    person_id: UUID | None = None
    object_id: UUID | None = None
    location_label: str | None = Field(default=None, max_length=120)
    action_label: str = Field(min_length=1, max_length=500)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    metadata: dict = Field(default_factory=dict)
    clip_path: str | None = Field(default=None, max_length=2048)

    @field_validator("timestamp")
    @classmethod
    def _timestamp_utc(cls, value: datetime) -> datetime:
        return to_utc(value)

    @field_validator("metadata")
    @classmethod
    def _bounded_metadata(cls, value: dict) -> dict:
        try:
            encoded = json.dumps(value, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise ValueError("metadata must be JSON serializable") from exc
        if len(encoded) > 16384:
            raise ValueError("metadata exceeds the 16 KiB limit")
        return value

    def to_text(self) -> str:
        """Human-readable event description for LLM context."""
        parts = [f"[{self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}]"]
        parts.append(self.action_label)
        object_category = self.metadata.get("object_category")
        if (
            isinstance(object_category, str)
            and object_category.strip()
            and object_category.lower() not in self.action_label.lower()
        ):
            parts.append(f"item: {object_category.strip()}")
        if self.location_label:
            parts.append(f"at {self.location_label}")
        if self.confidence < 0.8:
            parts.append(f"(confidence: {self.confidence:.0%})")
        return " ".join(parts)
