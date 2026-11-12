"""Camera management routes."""

from __future__ import annotations

import json
from typing import Annotated
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from uuid import UUID

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
_SECRET_URL_KEYS = {
    "accesstoken", "apikey", "auth", "authorization", "password", "secret",
    "signature", "token",
}
_URL_CONFIG_KEYS = {
    "whepurl", "rtspurl", "streamurl", "apiurl", "commandurl", "tokenurl",
}
_MAX_PROVIDER_CONFIG_BYTES = 16 * 1024


def _normalized_key(key: object) -> str:
    return "".join(char for char in str(key).lower() if char.isalnum())


def _is_secret_key(key: object) -> bool:
    normalized = _normalized_key(key)
    return normalized in {
        "accesstoken", "apikey", "auth", "authorization", "clientsecret",
        "password", "secret", "signature", "token",
    } or normalized.endswith("token")


def _validate_endpoint_value(value: str) -> None:
    parsed = urlparse(value)
    if parsed.username or parsed.password or parsed.fragment:
        raise ValueError("provider endpoint must not contain embedded credentials")
    if any(
        "".join(char for char in key.lower() if char.isalnum()) in _SECRET_URL_KEYS
        for key, _ in parse_qsl(parsed.query, keep_blank_values=True)
    ):
        raise ValueError(
            "provider endpoint must not contain credential-like query parameters"
        )


def _validate_provider_config(v: dict) -> dict:
    def contains_secret(value: object) -> bool:
        if isinstance(value, dict):
            return any(
                _is_secret_key(key) or contains_secret(child)
                for key, child in value.items()
            )
        if isinstance(value, list):
            return any(contains_secret(child) for child in value)
        return False

    try:
        encoded = json.dumps(v, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValueError("provider_config must contain JSON values") from exc
    if len(encoded) > _MAX_PROVIDER_CONFIG_BYTES:
        raise ValueError("provider_config exceeds the 16 KiB limit")

    if contains_secret(v):
        raise ValueError(
            "provider_config may contain endpoints and IDs only; keep credentials in environment variables"
        )

    def inspect_urls(value: object, key: str = "") -> None:
        normalized_key = _normalized_key(key)
        if normalized_key in _URL_CONFIG_KEYS and isinstance(value, str):
            _validate_endpoint_value(value.strip())
        elif isinstance(value, dict):
            for child_key, child_value in value.items():
                inspect_urls(child_value, str(child_key))
        elif isinstance(value, list):
            for child_value in value:
                inspect_urls(child_value, key)

    inspect_urls(v)
    return v


def _redact_url(value: str) -> str:
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        return value
    query = [
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if _normalized_key(key) not in _SECRET_URL_KEYS
    ]
    netloc = parsed.netloc.rsplit("@", 1)[-1]
    return urlunparse(
        (parsed.scheme, netloc, parsed.path, parsed.params, urlencode(query), "")
    )


def _redact_provider_config(value: object, key: str = "") -> object:
    if isinstance(value, dict):
        return {
            str(child_key): _redact_provider_config(child_value, str(child_key))
            for child_key, child_value in value.items()
            if not _is_secret_key(child_key)
        }
    if isinstance(value, list):
        return [_redact_provider_config(item, key) for item in value]
    if _normalized_key(key) in _URL_CONFIG_KEYS and isinstance(value, str):
        return _redact_url(value)
    return value


class CameraCreate(BaseModel):
    name: str = Field(max_length=120)
    stream_url: str = Field(max_length=2048)
    protocol: str = "rtsp"
    location_label: str | None = Field(default=None, max_length=120)
    # Keep the legacy field readable, but the bundled deployment has no
    # external edge-agent protocol that could process such a camera.
    is_edge_only: bool = False
    provider_config: dict = Field(default_factory=dict)

    @field_validator("protocol")
    @classmethod
    def _valid_protocol(cls, v: str) -> str:
        if v not in _PROTOCOLS:
            opts = ", ".join(sorted(_PROTOCOLS))
            raise ValueError(f"protocol must be one of: {opts}")
        return v

    @field_validator("is_edge_only")
    @classmethod
    def _edge_agent_required(cls, value: bool) -> bool:
        if value:
            raise ValueError(
                "edge-only cameras require an external edge agent, which is not bundled"
            )
        return value

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
        if parsed.fragment or any(
            "".join(char for char in key.lower() if char.isalnum()) in _SECRET_URL_KEYS
            for key, _ in parse_qsl(parsed.query, keep_blank_values=True)
        ):
            raise ValueError(
                "stream_url must not contain credential-like query parameters"
            )
        return v

    @field_validator("provider_config")
    @classmethod
    def _provider_config_has_no_secrets(cls, v: dict) -> dict:
        return _validate_provider_config(v)


class CameraUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    location_label: str | None = Field(default=None, max_length=120)
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


def _public_camera(row: asyncpg.Record | dict) -> CameraOut:
    data = dict(row)
    data["stream_url"] = _redact_url(str(data["stream_url"]))
    data["provider_config"] = _redact_provider_config(data["provider_config"] or {})
    return CameraOut(**data)


@router.get("", response_model=list[CameraOut])
async def list_cameras(user: CurrentUser, db: DB) -> list[CameraOut]:
    rows = await db.fetch(
        "SELECT * FROM cameras WHERE owner_id = $1 ORDER BY created_at",
        user["sub"],
    )
    return [_public_camera(r) for r in rows]


@router.post("", response_model=CameraOut, status_code=201)
async def add_camera(
    req: CameraCreate, user: CurrentUser, db: DB
) -> CameraOut:
    # Serialize quota check + insert per owner so concurrent requests cannot
    # create more cameras than the subscription allows.
    async with db.transaction():
        await db.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended($1::text, 0))",
            user["sub"],
        )
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
    return _public_camera(row)


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
    return _public_camera(row)


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
