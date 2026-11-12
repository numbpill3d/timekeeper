"""Event timeline routes."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..auth import CurrentUser
from ..db import get_db
from ..media import safe_signed_clip_url

router = APIRouter()

DB = Annotated[asyncpg.Connection, Depends(get_db)]


class EventOut(BaseModel):
    id: UUID
    camera_id: UUID
    event_type: str
    timestamp: datetime
    action_label: str
    location_label: str | None
    confidence: float
    clip_path: str | None
    person_label: str | None
    object_label: str | None


@router.get("", response_model=list[EventOut])
async def list_events(
    user: CurrentUser,
    db: DB,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    event_type: str | None = None,
    person_id: UUID | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[EventOut]:
    filters = [
        "e.camera_id IN (SELECT id FROM cameras WHERE owner_id = $1)"
    ]
    params: list = [user["sub"]]
    idx = 2

    if event_type:
        filters.append(f"e.event_type = ${idx}")
        params.append(event_type)
        idx += 1
    if person_id:
        filters.append(f"e.person_id = ${idx}")
        params.append(person_id)
        idx += 1
    if since:
        filters.append(f"e.timestamp >= ${idx}")
        params.append(since)
        idx += 1
    if until:
        filters.append(f"e.timestamp <= ${idx}")
        params.append(until)
        idx += 1

    where = " AND ".join(filters)
    params += [limit, offset]

    rows = await db.fetch(
        f"""
        SELECT e.id, e.camera_id, e.event_type, e.timestamp,
               e.action_label, e.location_label, e.confidence, e.clip_path,
               p.label AS person_label,
               o.label AS object_label
        FROM events e
        LEFT JOIN persons p ON e.person_id = p.id
        LEFT JOIN tracked_objects o ON e.object_id = o.id
        WHERE {where}
        ORDER BY e.timestamp DESC
        LIMIT ${idx} OFFSET ${idx + 1}
        """,
        *params,
    )
    return [
        EventOut(**{**dict(r), "clip_path": safe_signed_clip_url(r["clip_path"])})
        for r in rows
    ]


@router.get("/{event_id}", response_model=EventOut)
async def get_event(
    event_id: UUID, user: CurrentUser, db: DB
) -> EventOut:
    row = await db.fetchrow(
        """
        SELECT e.*, p.label AS person_label, o.label AS object_label
        FROM events e
        LEFT JOIN persons p ON e.person_id = p.id
        LEFT JOIN tracked_objects o ON e.object_id = o.id
        WHERE e.id = $1
          AND e.camera_id IN (SELECT id FROM cameras WHERE owner_id = $2)
        """,
        event_id,
        user["sub"],
    )
    if not row:
        raise HTTPException(status_code=404, detail="event not found")
    return EventOut(
        **{**dict(row), "clip_path": safe_signed_clip_url(row["clip_path"])}
    )
