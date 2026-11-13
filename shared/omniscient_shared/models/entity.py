from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from omniscient_shared.time import to_utc


class Detection(BaseModel):
    """Single detection from the CV pipeline for one frame."""
    camera_id: UUID
    timestamp: datetime
    frame_id: str = Field(min_length=1, max_length=200)
    track_id: int = Field(ge=0)
    class_name: str = Field(min_length=1, max_length=80)
    confidence: float = Field(ge=0.0, le=1.0)
    bbox: tuple[float, float, float, float]  # x1,y1,x2,y2 normalized 0-1
    person_id: UUID | None = None
    object_id: UUID | None = None
    association_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    association_method: str | None = Field(default=None, max_length=80)

    @field_validator("timestamp")
    @classmethod
    def _timestamp_utc(cls, value: datetime) -> datetime:
        return to_utc(value)

    @model_validator(mode="after")
    def _valid_bbox(self) -> Detection:
        x1, y1, x2, y2 = self.bbox
        if not all(0.0 <= value <= 1.0 for value in self.bbox):
            raise ValueError("bbox coordinates must be normalized between 0 and 1")
        if x2 <= x1 or y2 <= y1:
            raise ValueError("bbox must have positive area")
        return self


class FrameMessage(BaseModel):
    """Published by ingestion to the 'frames' topic."""
    camera_id: UUID
    timestamp: datetime
    frame_id: str = Field(min_length=1, max_length=200)
    frame_path: str = Field(min_length=1, max_length=1024)  # shared-volume path
    width: int = Field(gt=0, le=16384)
    height: int = Field(gt=0, le=16384)

    @field_validator("timestamp")
    @classmethod
    def _timestamp_utc(cls, value: datetime) -> datetime:
        return to_utc(value)


class DetectionMessage(BaseModel):
    """Published by vision to the 'detections' topic."""
    camera_id: UUID
    timestamp: datetime
    frame_id: str = Field(min_length=1, max_length=200)
    frame_path: str | None = Field(default=None, max_length=1024)  # propagated from FrameMessage for clip extraction
    detections: list[Detection] = Field(default_factory=list, max_length=512)

    @field_validator("timestamp")
    @classmethod
    def _timestamp_utc(cls, value: datetime) -> datetime:
        return to_utc(value)

    @model_validator(mode="after")
    def _detections_match_frame(self) -> DetectionMessage:
        for detection in self.detections:
            if detection.camera_id != self.camera_id:
                raise ValueError("detection camera_id must match message camera_id")
            if detection.frame_id != self.frame_id:
                raise ValueError("detection frame_id must match message frame_id")
        return self


class Person(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    owner_id: UUID
    label: str = Field(min_length=1, max_length=120)
    is_known: bool = False
    appearance_tags: list[str] = Field(default_factory=list)
    retention_days: int = Field(default=30, ge=1, le=3650)
    last_seen_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TrackedObject(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    owner_id: UUID
    category: str = Field(min_length=1, max_length=80)
    label: str | None = Field(default=None, max_length=120)
    last_camera_id: UUID | None = None
    last_seen_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
