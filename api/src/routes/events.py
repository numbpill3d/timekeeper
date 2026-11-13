"""Event timeline routes."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from omniscient_shared.time import to_utc
from pydantic import BaseModel, Field

from ..audit import record_audit
from ..auth import CurrentUser
from ..db import get_db
from ..media import delete_clip_objects, safe_signed_clip_url

router = APIRouter()

DB = Annotated[asyncpg.Connection, Depends(get_db)]


class EventOut(BaseModel):
    id: UUID
    camera_id: UUID
    camera_name: str
    event_type: str
    timestamp: datetime
    action_label: str
    location_label: str | None
    confidence: float
    clip_path: str | None
    person_label: str | None
    object_label: str | None
    annotation: str | None = None


class AnnotationUpdate(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


class AnnotationOut(BaseModel):
    note: str | None
    updated_at: datetime | None


class EventCountOut(BaseModel):
    count: int


def _event_filters(
    user_id: str,
    event_type: str | None,
    person_id: UUID | None,
    since: datetime | None,
    until: datetime | None,
    search: str | None = None,
    camera_id: UUID | None = None,
) -> tuple[str, list[object]]:
    filters = [
        "e.camera_id IN (SELECT id FROM cameras WHERE owner_id = $1)"
    ]
    params: list[object] = [user_id]

    for expression, value in (
        ("e.event_type =", event_type),
        ("e.person_id =", person_id),
        ("e.camera_id =", camera_id),
        ("e.timestamp >=", since),
        ("e.timestamp <=", until),
    ):
        if value is not None:
            if isinstance(value, datetime):
                value = to_utc(value)
            placeholder = len(params) + 1
            filters.append(f"{expression} ${placeholder}")
            params.append(value)
    if isinstance(search, str) and search.strip():
        placeholder = len(params) + 1
        term = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        params.append(f"%{term}%")
        filters.append(
            f"(e.event_type ILIKE ${placeholder} ESCAPE E'\\\\' "
            f"OR e.action_label ILIKE ${placeholder} ESCAPE E'\\\\' "
            f"OR e.location_label ILIKE ${placeholder} ESCAPE E'\\\\' "
            f"OR EXISTS (SELECT 1 FROM event_annotations ea WHERE ea.event_id = e.id "
            f"AND ea.owner_id = $1 AND ea.note ILIKE ${placeholder} ESCAPE E'\\\\') "
            "OR EXISTS (SELECT 1 FROM persons ps WHERE ps.id = e.person_id "
            f"AND ps.owner_id = $1 AND ps.label ILIKE ${placeholder} ESCAPE E'\\\\') "
            "OR EXISTS (SELECT 1 FROM tracked_objects os WHERE os.id = e.object_id "
            f"AND os.owner_id = $1 AND (os.label ILIKE ${placeholder} ESCAPE E'\\\\' "
            f"OR os.category ILIKE ${placeholder} ESCAPE E'\\\\')))"
        )
    return " AND ".join(filters), params


@router.get("", response_model=list[EventOut])
async def list_events(
    user: CurrentUser,
    db: DB,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    event_type: str | None = None,
    person_id: UUID | None = None,
    camera_id: UUID | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    search: str | None = Query(None, min_length=1, max_length=120),
) -> list[EventOut]:
    where, params = _event_filters(
        user["sub"], event_type, person_id, since, until, search, camera_id
    )
    limit_idx = len(params) + 1
    params += [limit, offset]

    rows = await db.fetch(
        f"""
        SELECT e.id, e.camera_id, c.name AS camera_name, e.event_type, e.timestamp,
               e.action_label, e.location_label, e.confidence, e.clip_path,
               p.label AS person_label,
               COALESCE(o.label, o.category) AS object_label,
               ea.note AS annotation
        FROM events e
        JOIN cameras c ON c.id = e.camera_id AND c.owner_id = $1
        LEFT JOIN persons p ON e.person_id = p.id AND p.owner_id = $1
        LEFT JOIN tracked_objects o ON e.object_id = o.id AND o.owner_id = $1
        LEFT JOIN event_annotations ea
          ON ea.event_id = e.id AND ea.owner_id = $1
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
    camera_id: UUID | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    search: str | None = Query(None, min_length=1, max_length=120),
) -> EventCountOut:
    where, params = _event_filters(
        user["sub"], event_type, person_id, since, until, search, camera_id
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
        SELECT e.*, c.name AS camera_name, p.label AS person_label,
               COALESCE(o.label, o.category) AS object_label,
               ea.note AS annotation
        FROM events e
        JOIN cameras c ON c.id = e.camera_id AND c.owner_id = $2
        LEFT JOIN persons p ON e.person_id = p.id AND p.owner_id = $2
        LEFT JOIN tracked_objects o ON e.object_id = o.id AND o.owner_id = $2
        LEFT JOIN event_annotations ea
          ON ea.event_id = e.id AND ea.owner_id = $2
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


@router.patch("/{event_id}/annotation", response_model=AnnotationOut)
async def update_event_annotation(
    event_id: UUID,
    payload: AnnotationUpdate,
    user: CurrentUser,
    db: DB,
) -> AnnotationOut:
    """Create, replace, or clear one owner's review note for an event."""
    note = payload.note.strip() if payload.note is not None else ""
    async with db.transaction():
        exists = await db.fetchval(
            """
            SELECT EXISTS(
                SELECT 1 FROM events e
                JOIN cameras c ON c.id = e.camera_id AND c.owner_id = $2
                WHERE e.id = $1
            )
            """,
            event_id,
            user["sub"],
        )
        if not exists:
            raise HTTPException(status_code=404, detail="event not found")
        if note:
            row = await db.fetchrow(
                """
                INSERT INTO event_annotations (event_id, owner_id, note)
                VALUES ($1, $2, $3)
                ON CONFLICT (event_id, owner_id) DO UPDATE
                SET note = EXCLUDED.note, updated_at = NOW()
                RETURNING note, updated_at
                """,
                event_id,
                user["sub"],
                note,
            )
            action = "annotate"
        else:
            await db.execute(
                "DELETE FROM event_annotations WHERE event_id = $1 AND owner_id = $2",
                event_id,
                user["sub"],
            )
            row = None
            action = "clear_annotation"
        await record_audit(db, user["sub"], action, "event", event_id)
    return AnnotationOut(**(dict(row) if row else {"note": None, "updated_at": None}))


@router.delete("/{event_id}", status_code=204)
async def redact_event(
    event_id: UUID, user: CurrentUser, db: DB
) -> Response:
    """Permanently remove one event and its clip, while auditing the action."""
    async with db.transaction():
        row = await db.fetchrow(
            """
            SELECT e.id, e.camera_id, e.clip_path, e.event_type, e.timestamp
            FROM events e
            JOIN cameras c ON c.id = e.camera_id AND c.owner_id = $2
            WHERE e.id = $1
            FOR UPDATE
            """,
            event_id,
            user["sub"],
        )
        if not row:
            raise HTTPException(status_code=404, detail="event not found")
        await db.execute("DELETE FROM alert_deliveries WHERE event_id = $1", event_id)
        await db.execute("DELETE FROM event_annotations WHERE event_id = $1", event_id)
        await db.execute("DELETE FROM events WHERE id = $1", event_id)
        await record_audit(
            db,
            user["sub"],
            "redact",
            "event",
            event_id,
            {"camera_id": str(row["camera_id"]), "event_type": row["event_type"]},
        )
    await delete_clip_objects([row["clip_path"]])
    return Response(status_code=204)
