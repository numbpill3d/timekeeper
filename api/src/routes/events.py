"""Event timeline routes."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query
from omniscient_shared.time import to_utc
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


class EventCountOut(BaseModel):
    count: int


def _event_filters(
    user_id: str,
    event_type: str | None,
    person_id: UUID | None,
    since: datetime | None,
    until: datetime | None,
) -> tuple[str, list[object]]:
    filters = [
        "e.camera_id IN (SELECT id FROM cameras WHERE owner_id = $1)"
    ]
    params: list[object] = [user_id]

    for expression, value in (
        ("e.event_type =", event_type),
        ("e.person_id =", person_id),
        ("e.timestamp >=", since),
        ("e.timestamp <=", until),
    ):
        if value is not None:
            if isinstance(value, datetime):
                value = to_utc(value)
            placeholder = len(params) + 1
            filters.append(f"{expression} ${placeholder}")
            params.append(value)
    return " AND ".join(filters), params


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
    where, params = _event_filters(
        user["sub"], event_type, person_id, since, until
    )
    limit_idx = len(params) + 1
    params += [limit, offset]

    rows = await db.fetch(
        f"""
        SELECT e.id, e.camera_id, e.event_type, e.timestamp,
               e.action_label, e.location_label, e.confidence, e.clip_path,
               p.label AS person_label,
               o.label AS object_label
        FROM events e
        LEFT JOIN persons p ON e.person_id = p.id AND p.owner_id = $1
        LEFT JOIN tracked_objects o ON e.object_id = o.id AND o.owner_id = $1
        WHERE {where}
        ORDER BY e.timestamp DESC, e.id DESC
        LIMIT ${limit_idx} OFFSET ${limit_idx + 1}
        """,
        *params,
    )
    return [
        EventOut(**{**dict(r), "clip_path": safe_signed_clip_url(r["clip_path"])})
        for r in rows
    ]


@router.get("/count", response_model=EventCountOut)
async def count_events(
    user: CurrentUser,
    db: DB,
    event_type: str | None = None,
    person_id: UUID | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> EventCountOut:
    where, params = _event_filters(
        user["sub"], event_type, person_id, since, until
    )
    count = await db.fetchval(
        f"SELECT COUNT(*) FROM events e WHERE {where}",
        *params,
    )
    return EventCountOut(count=int(count or 0))


@router.get("/{event_id}", response_model=EventOut)
async def get_event(
    event_id: UUID, user: CurrentUser, db: DB
) -> EventOut:
    row = await db.fetchrow(
        """
        SELECT e.*, p.label AS person_label, o.label AS object_label
        FROM events e
        LEFT JOIN persons p ON e.person_id = p.id AND p.owner_id = $2
        LEFT JOIN tracked_objects o ON e.object_id = o.id AND o.owner_id = $2
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
