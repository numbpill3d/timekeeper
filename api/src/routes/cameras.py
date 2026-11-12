"""Camera management routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID
from urllib.parse import urlparse

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from ..auth import CurrentUser
from ..db import get_db

router = APIRouter()

DB = Annotated[asyncpg.Connection, Depends(get_db)]

_TIER_LIMITS = {"free": 2, "home": 5, "family": 10, "pro": 9999}
_PROTOCOLS = {"rtsp", "http", "https", "hls", "file", "onvif", "ring", "nest", "arlo", "wyze"}
_UPDATE_ALLOWED = {"name", "location_label", "is_active", "provider_config"}


def _validate_provider_config(v: dict) -> dict:
    forbidden = {
        "accesstoken", "clientsecret", "password", "secret", "token",
    }

    def is_secret_key(key: object) -> bool:
        normalized = "".join(char for char in str(key).lower() if char.isalnum())
        return normalized in forbidden or normalized.endswith("token")

    def contains_secret(value: object) -> bool:
        if isinstance(value, dict):
            return any(
                is_secret_key(key) or contains_secret(child)
                for key, child in value.items()
            )
        if isinstance(value, list):
            return any(contains_secret(child) for child in value)
        return False

    if contains_secret(v):
        raise ValueError(
            "provider_config may contain endpoints and IDs only; keep credentials in environment variables"
        )
    return v


class CameraCreate(BaseModel):
    name: str
    stream_url: str
    protocol: str = "rtsp"
    location_label: str | None = None
    is_edge_only: bool = False
    provider_config: dict = Field(default_factory=dict)

    @field_validator("protocol")
    @classmethod
    def _valid_protocol(cls, v: str) -> str:
        if v not in _PROTOCOLS:
            opts = ", ".join(sorted(_PROTOCOLS))
            raise ValueError(f"protocol must be one of: {opts}")
        return v

    @field_validator("name")
    @classmethod
    def _nonempty_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name cannot be empty")
        return v

    @field_validator("stream_url")
    @classmethod
    def _valid_stream_url(cls, v: str) -> str:
        v = v.strip()
        parsed = urlparse(v)
        if parsed.scheme not in {
            "rtsp", "rtsps", "http", "https", "file",
            "ring", "nest", "arlo", "wyze",
        }:
            raise ValueError(
                "stream_url must be a direct stream URL or ring://, nest://, "
                "arlo://, or wyze:// device URL"
            )
        if parsed.scheme != "file" and not parsed.netloc:
            raise ValueError("stream_url must include a host")
        if parsed.username or parsed.password:
            raise ValueError(
                "stream_url must not contain embedded credentials; use secret files"
            )
        return v

    @field_validator("provider_config")
    @classmethod
    def _provider_config_has_no_secrets(cls, v: dict) -> dict:
        return _validate_provider_config(v)


class CameraUpdate(BaseModel):
    name: str | None = None
    location_label: str | None = None
    is_active: bool | None = None
    provider_config: dict | None = None

    @field_validator("provider_config")
    @classmethod
    def _safe_provider_config(cls, v: dict | None) -> dict | None:
        return _validate_provider_config(v) if v is not None else None


class CameraOut(BaseModel):
    id: UUID
    name: str
    stream_url: str
    protocol: str
    location_label: str | None
    is_edge_only: bool
    is_active: bool
    provider_config: dict


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
            (owner_id, name, stream_url, protocol, location_label, is_edge_only, provider_config)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING *
        """,
        user["sub"],
        req.name,
        req.stream_url,
        req.protocol,
        req.location_label,
        req.is_edge_only,
        req.provider_config,
    )
    return CameraOut(**dict(row))


@router.patch("/{camera_id}", response_model=CameraOut)
async def update_camera(
    camera_id: UUID, req: CameraUpdate, user: CurrentUser, db: DB
) -> CameraOut:
    updates = {k: v for k, v in req.model_dump(exclude_none=True).items()
               if k in _UPDATE_ALLOWED}
    if not updates:
        raise HTTPException(status_code=422, detail="no fields to update")
    sets = ", ".join(f"{col} = ${i + 3}" for i, col in enumerate(updates))
    result = await db.execute(
        f"UPDATE cameras SET {sets} WHERE id = $1 AND owner_id = $2",
        camera_id,
        user["sub"],
        *updates.values(),
    )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="camera not found")
    row = await db.fetchrow("SELECT * FROM cameras WHERE id = $1", camera_id)
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
