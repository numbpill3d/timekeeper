from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel


class CameraProtocol(str, Enum):
    rtsp = "rtsp"
    onvif = "onvif"
    ring = "ring"
    nest = "nest"
    arlo = "arlo"
    wyze = "wyze"


class Camera(BaseModel):
    id: UUID = uuid4()
    owner_id: UUID
    name: str
    stream_url: str
    protocol: CameraProtocol = CameraProtocol.rtsp
    location_label: str | None = None
    is_edge_only: bool = False
    is_active: bool = True
    created_at: datetime = datetime.utcnow()
