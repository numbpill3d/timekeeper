from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

# Phase 1 object detection categories (expandable in later phases)
TRACKABLE_OBJECTS = frozenset({
    "keys", "wallet", "phone", "bag", "backpack", "package",
    "laptop", "tablet", "glasses", "medication", "bottle",
    "person", "dog", "cat", "car", "bicycle",
})


class Detection(BaseModel):
    """Single detection from the CV pipeline for one frame."""
    camera_id: UUID
    timestamp: datetime
    frame_id: str
    track_id: int
    class_name: str
    confidence: float
    bbox: tuple[float, float, float, float]  # x1,y1,x2,y2 normalized 0-1
    person_id: UUID | None = None
    object_id: UUID | None = None


class FrameMessage(BaseModel):
    """Published by ingestion to the 'frames' topic."""
    camera_id: UUID
    timestamp: datetime
    frame_id: str
    frame_path: str        # path in shared volume or S3 key
    width: int
    height: int


class DetectionMessage(BaseModel):
    """Published by vision to the 'detections' topic."""
    camera_id: UUID
    timestamp: datetime
    frame_id: str
    frame_path: str | None = None  # propagated from FrameMessage for clip extraction
    detections: list[Detection] = Field(default_factory=list)


class Person(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    owner_id: UUID
    label: str
    is_known: bool = False
    appearance_tags: list[str] = Field(default_factory=list)
    retention_days: int = 30
    last_seen_at: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TrackedObject(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    owner_id: UUID
    category: str
    label: str | None = None
    last_camera_id: UUID | None = None
    last_seen_at: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
