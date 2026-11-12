from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class CameraProtocol(str, Enum):
    rtsp = "rtsp"
    http = "http"
    https = "https"
    hls = "hls"
    file = "file"
    onvif = "onvif"
    ring = "ring"
    nest = "nest"
    arlo = "arlo"
    wyze = "wyze"


class Camera(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    owner_id: UUID
    name: str
    stream_url: str
    protocol: CameraProtocol = CameraProtocol.rtsp
    location_label: str | None = None
    is_edge_only: bool = False
    is_active: bool = True
    provider_config: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
