"""Read-only retention impact previews."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Annotated
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..auth import CurrentUser
from ..db import get_db

router = APIRouter()
DB = Annotated[asyncpg.Connection, Depends(get_db)]
_DEFAULT_RETENTION_DAYS = max(1, int(os.getenv("DEFAULT_RETENTION_DAYS", "30")))


class RetentionPreviewOut(BaseModel):
    camera_id: UUID
    camera_name: str
    events_expiring: int
    detections_expiring: int
    oldest_event_at: datetime | None = None


@router.get("/preview", response_model=list[RetentionPreviewOut])
async def retention_preview(
    user: CurrentUser, db: DB
) -> list[RetentionPreviewOut]:
    """Report what the next retention sweep could remove, without mutating data."""
    rows = await db.fetch(
        """
        WITH event_counts AS (
            SELECT e.camera_id,
                   COUNT(*) FILTER (WHERE e.timestamp < NOW() - make_interval(
                       days => COALESCE(p.retention_days, ec.retention_days, $2))) AS events_expiring,
                   MIN(e.timestamp) FILTER (WHERE e.timestamp < NOW() - make_interval(
                       days => COALESCE(p.retention_days, ec.retention_days, $2))) AS oldest_event_at
            FROM events e
            JOIN cameras ec ON ec.id = e.camera_id AND ec.owner_id = $1
            LEFT JOIN persons p ON p.id = e.person_id AND p.owner_id = $1
            GROUP BY e.camera_id
        ), detection_counts AS (
            SELECT d.camera_id,
                   COUNT(*) FILTER (WHERE d.timestamp < NOW() - make_interval(
                       days => COALESCE(p.retention_days, dc.retention_days, $2))) AS detections_expiring
            FROM detections d
            JOIN cameras dc ON dc.id = d.camera_id AND dc.owner_id = $1
            LEFT JOIN persons p ON p.id = d.person_id AND p.owner_id = $1
            GROUP BY d.camera_id
        )
        SELECT c.id AS camera_id, c.name AS camera_name,
               COALESCE(ec.events_expiring, 0)::int AS events_expiring,
               COALESCE(dc.detections_expiring, 0)::int AS detections_expiring,
               ec.oldest_event_at
        FROM cameras c
        LEFT JOIN event_counts ec ON ec.camera_id = c.id
        LEFT JOIN detection_counts dc ON dc.camera_id = c.id
        WHERE c.owner_id = $1
        ORDER BY c.name, c.id
        """,
        user["sub"],
        _DEFAULT_RETENTION_DAYS,
    )
    return [RetentionPreviewOut(**dict(row)) for row in rows]
