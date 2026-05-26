from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


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
    location_label: str | None = None
    action_label: str
    confidence: float = 1.0
    metadata: dict = Field(default_factory=dict)
    clip_path: str | None = None

    def to_text(self) -> str:
        """Human-readable event description for LLM context."""
        parts = [f"[{self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}]"]
        parts.append(self.action_label)
        if self.location_label:
            parts.append(f"at {self.location_label}")
        if self.confidence < 0.8:
            parts.append(f"(confidence: {self.confidence:.0%})")
        return " ".join(parts)
