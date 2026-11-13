"""Camera management routes."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from typing import Annotated
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator

from ..audit import record_audit
from ..auth import CurrentUser
from ..db import get_db
from ..media import delete_clip_objects

router = APIRouter()

DB = Annotated[asyncpg.Connection, Depends(get_db)]

_TIER_LIMITS = {"free": 2, "home": 5, "family": 10, "pro": 9999}
_PROTOCOLS = {"rtsp", "http", "https", "hls", "file", "onvif", "ring", "nest", "arlo", "wyze"}
_DEVICE_PROTOCOLS = {"ring", "nest", "arlo", "wyze"}
_DIRECT_SCHEME_PROTOCOLS = {
    "rtsp": "rtsp",
    "rtsps": "rtsp",
    "http": "http",
    "https": "https",
    "file": "file",
}
_UPDATE_ALLOWED = {
    "name", "stream_url", "protocol", "location_label", "is_active", "provider_config"
}
_URL_CONFIG_KEYS = {
    "whepurl", "rtspurl", "streamurl", "apiurl", "commandurl", "tokenurl",
}
_MAX_PROVIDER_CONFIG_BYTES = 16 * 1024
_CAMERA_STALE_AFTER = timedelta(seconds=45)
_DEFAULT_RETENTION_DAYS = max(1, int(os.getenv("DEFAULT_RETENTION_DAYS", "30")))


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
    if any(_is_secret_key(key) for key, _ in parse_qsl(parsed.query, keep_blank_values=True)):
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
        if not _is_secret_key(key)
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
            _is_secret_key(key)
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

    @model_validator(mode="after")
    def _align_device_protocol(self) -> CameraCreate:
        scheme = urlparse(self.stream_url).scheme
        if scheme in _DEVICE_PROTOCOLS:
            if self.protocol == "rtsp":
                # The default is retained for ordinary direct feeds, but a
                # device URL is unambiguous and must reach its provider adapter.
                self.protocol = scheme
            elif self.protocol != scheme:
                raise ValueError(
                    f"{scheme}:// sources must use protocol={scheme!r}"
                )
        expected = _DIRECT_SCHEME_PROTOCOLS.get(scheme)
        if expected and self.protocol == "rtsp" and expected != "rtsp":
            # rtsp is the backwards-compatible default, so infer a more
            # specific direct-feed adapter only when the caller omitted it.
            if "protocol" in self.model_fields_set:
                raise ValueError(
                    f"{scheme}:// sources must use protocol={expected!r}"
                )
            self.protocol = expected
        elif expected and self.protocol not in (
            {expected, "hls"} if scheme in {"http", "https"} else {expected}
        ):
            raise ValueError(
                f"{scheme}:// sources must use protocol={expected!r}"
            )
        return self


class CameraUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    stream_url: str | None = Field(default=None, max_length=2048)
    protocol: str | None = None
    location_label: str | None = Field(default=None, max_length=120)
    is_active: bool | None = None
    provider_config: dict | None = None

    @field_validator("protocol")
    @classmethod
    def _valid_protocol(cls, v: str | None) -> str | None:
        if v is not None and v not in _PROTOCOLS:
            opts = ", ".join(sorted(_PROTOCOLS))
            raise ValueError(f"protocol must be one of: {opts}")
        return v

    @field_validator("stream_url")
    @classmethod
    def _valid_stream_url(cls, v: str | None) -> str | None:
        if v is None:
            return None
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
            _is_secret_key(key)
            for key, _ in parse_qsl(parsed.query, keep_blank_values=True)
        ):
            raise ValueError(
                "stream_url must not contain credential-like query parameters"
            )
        return v

    @field_validator("provider_config")
    @classmethod
    def _safe_provider_config(cls, v: dict | None) -> dict | None:
        return _validate_provider_config(v) if v is not None else None

    @field_validator("name")
    @classmethod
    def _nonempty_name(cls, v: str | None) -> str | None:
        v = v.strip() if v is not None else None
        if v == "":
            raise ValueError("name cannot be empty")
        return v

    @field_validator("location_label")
    @classmethod
    def _strip_location(cls, v: str | None) -> str | None:
        v = v.strip() if v is not None else None
        return v or None

    @model_validator(mode="after")
    def _align_device_protocol(self) -> CameraUpdate:
        if self.stream_url is None:
            return self
        scheme = urlparse(self.stream_url).scheme
        if scheme in _DEVICE_PROTOCOLS:
            if self.protocol is None:
                # A partial update that changes only the source still needs
                # the matching adapter persisted with it.
                self.protocol = scheme
            elif self.protocol != scheme:
                raise ValueError(
                    f"{scheme}:// sources must use protocol={scheme!r}"
                )
        expected = _DIRECT_SCHEME_PROTOCOLS.get(scheme)
        if expected and (
            self.protocol is None
            or (self.protocol == "rtsp" and expected != "rtsp")
        ):
            if self.protocol == "rtsp" and "protocol" in self.model_fields_set:
                raise ValueError(
                    f"{scheme}:// sources must use protocol={expected!r}"
                )
            self.protocol = expected
        elif expected and self.protocol not in (
            {expected, "hls"} if scheme in {"http", "https"} else {expected}
        ):
            raise ValueError(
                f"{scheme}:// sources must use protocol={expected!r}"
            )
        return self


class CameraOut(BaseModel):
    id: UUID
    name: str
    stream_url: str
    protocol: str
    location_label: str | None
    is_edge_only: bool
    is_active: bool
    provider_config: dict
    status: str = "starting"
    last_frame_at: datetime | None = None
    last_error_at: datetime | None = None
    last_error_code: str | None = None
    consecutive_failures: int = 0
    last_frame_width: int | None = None
    last_frame_height: int | None = None
    observed_fps: float | None = None
    default_retention_days: int = _DEFAULT_RETENTION_DAYS


def _camera_status(data: dict, now: datetime | None = None) -> str:
    if not data.get("is_active", True):
        return "paused"
    last_frame = data.get("last_frame_at")
    last_error = data.get("last_error_at")
    if last_error is not None and (last_frame is None or last_error >= last_frame):
        return "error"
    if last_frame is None:
        return "starting"
    current = now or datetime.now(UTC)
    if current - last_frame <= _CAMERA_STALE_AFTER:
        return "online"
    return "stale"


def _public_camera(row: asyncpg.Record | dict) -> CameraOut:
    data = dict(row)
    data["status"] = _camera_status(data)
    data["stream_url"] = _redact_url(str(data["stream_url"]))
    data["provider_config"] = _redact_provider_config(data["provider_config"] or {})
    return CameraOut(**data)


@router.get("", response_model=list[CameraOut])
async def list_cameras(user: CurrentUser, db: DB) -> list[CameraOut]:
    rows = await db.fetch(
        "SELECT * FROM cameras WHERE owner_id = $1 ORDER BY created_at, id",
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
        tier = await db.fetchval(
            "SELECT subscription_tier FROM users WHERE id = $1 FOR UPDATE",
            user["sub"],
        )
        if tier is None:
            raise HTTPException(status_code=401, detail="user not found")
        count = await db.fetchval(
            "SELECT COUNT(*) FROM cameras WHERE owner_id = $1", user["sub"]
        )
        limit = _TIER_LIMITS.get(tier, 2)
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
    # `exclude_unset` keeps an explicit null location distinct from an omitted
    # field, allowing clients to clear a stale location label without turning
    # other nullable patch fields into invalid SQL values.
    updates = {
        k: v
        for k, v in req.model_dump(exclude_unset=True).items()
        if k in _UPDATE_ALLOWED and (v is not None or k == "location_label")
    }
    if not updates:
        raise HTTPException(status_code=422, detail="no fields to update")
    sets = ", ".join(f"{col} = ${i + 3}" for i, col in enumerate(updates))
    row = await db.fetchrow(
        f"UPDATE cameras SET {sets} "
        "WHERE id = $1 AND owner_id = $2 "
        "RETURNING *",
        camera_id,
        user["sub"],
        *updates.values(),
    )
    if not row:
        raise HTTPException(status_code=404, detail="camera not found")
    return _public_camera(row)


@router.delete("/{camera_id}", status_code=204)
async def delete_camera(
    camera_id: UUID, user: CurrentUser, db: DB
) -> None:
    # Camera history is keyed to the camera, so remove dependent rows in one
    # transaction before deleting the camera itself. Clip objects are removed
    # after commit because object storage cannot participate in this DB txn.
    async with db.transaction():
        camera_exists = await db.fetchval(
            "SELECT 1 FROM cameras WHERE id = $1 AND owner_id = $2 FOR UPDATE",
            camera_id,
            user["sub"],
        )
        if not camera_exists:
            raise HTTPException(status_code=404, detail="camera not found")
        events = await db.fetch(
            "SELECT id, clip_path FROM events WHERE camera_id = $1 FOR UPDATE",
            camera_id,
        )
        event_ids = [row["id"] for row in events]
        if event_ids:
            await db.execute(
                "DELETE FROM alert_deliveries WHERE event_id = ANY($1::uuid[])",
                event_ids,
            )
            await db.execute(
                "DELETE FROM event_annotations WHERE event_id = ANY($1::uuid[])",
                event_ids,
            )
        await db.execute("DELETE FROM detections WHERE camera_id = $1", camera_id)
        await db.execute("DELETE FROM events WHERE camera_id = $1", camera_id)
        await db.execute(
            "UPDATE tracked_objects SET last_camera_id = NULL "
            "WHERE last_camera_id = $1",
            camera_id,
        )
        await db.execute("DELETE FROM cameras WHERE id = $1", camera_id)
        await record_audit(
            db,
            user["sub"],
            "delete",
            "camera",
            camera_id,
            {"event_count": len(events)},
        )
    await delete_clip_objects([row["clip_path"] for row in events])
