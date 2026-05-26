"""Camera management routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import CurrentUser
from ..db import get_db

router = APIRouter()

DB = Annotated[asyncpg.Connection, Depends(get_db)]

_TIER_LIMITS = {"free": 2, "home": 5, "family": 10, "pro": 9999}


class CameraCreate(BaseModel):
    name: str
    stream_url: str
    protocol: str = "rtsp"
    location_label: str | None = None
    is_edge_only: bool = False


class CameraOut(BaseModel):
    id: UUID
    name: str
    stream_url: str
    protocol: str
    location_label: str | None
    is_edge_only: bool
    is_active: bool


@router.get("", response_model=list[CameraOut])
async def list_cameras(user: CurrentUser, db: DB) -> list[CameraOut]:
    rows = await db.fetch(
        "SELECT * FROM cameras WHERE owner_id = $1 ORDER BY created_at",
        user["sub"],
    )
    return [CameraOut(**dict(r)) for r in rows]


@router.post("", response_model=CameraOut, status_code=201)
async def add_camera(
    req: CameraCreate, user: CurrentUser, db: DB
) -> CameraOut:
    count = await db.fetchval(
        "SELECT COUNT(*) FROM cameras WHERE owner_id = $1", user["sub"]
    )
    limit = _TIER_LIMITS.get(user.get("tier", "free"), 2)
    if count >= limit:
        raise HTTPException(
            status_code=403,
            detail=f"camera limit ({limit}) reached for your plan",
        )

    row = await db.fetchrow(
        """
        INSERT INTO cameras
            (owner_id, name, stream_url, protocol, location_label, is_edge_only)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING *
        """,
        user["sub"],
        req.name,
        req.stream_url,
        req.protocol,
        req.location_label,
        req.is_edge_only,
    )
    return CameraOut(**dict(row))


@router.delete("/{camera_id}", status_code=204)
async def delete_camera(
    camera_id: UUID, user: CurrentUser, db: DB
) -> None:
    result = await db.execute(
        "DELETE FROM cameras WHERE id = $1 AND owner_id = $2",
        camera_id,
        user["sub"],
    )
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="camera not found")
