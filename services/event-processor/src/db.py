"""
Persist events to TimescaleDB and embed them for RAG via the query engine.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
from pathlib import Path
from uuid import UUID

import asyncpg
import boto3
import httpx
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from omniscient_shared.models.event import Event

from .storage import object_key

log = logging.getLogger(__name__)

_DB_URL = os.getenv("DATABASE_URL", "")
_QUERY_ENGINE = os.getenv("QUERY_ENGINE_URL", "http://query-engine:8001")
_S3_ENDPOINT = os.getenv("S3_ENDPOINT_URL", "http://minio:9000")
_S3_KEY = os.getenv("S3_ACCESS_KEY", "minioadmin")
_S3_SECRET = os.getenv("S3_SECRET_KEY", "minioadmin")
_BUCKET = os.getenv("MEDIA_BUCKET", "omniscient-media")
_FRAME_ROOT = Path(os.getenv("FRAME_STORE_PATH", "/tmp/frames")).resolve()
_DEFAULT_RETENTION_DAYS = max(
    1, int(os.getenv("DEFAULT_RETENTION_DAYS", "30"))
)

if os.getenv("ENVIRONMENT", "development").lower() == "production" and (
    not _S3_KEY or not _S3_SECRET or _S3_KEY == "minioadmin" or _S3_SECRET == "minioadmin"
):
    raise RuntimeError("production media storage credentials must be configured")

_s3 = boto3.client(
    "s3",
    endpoint_url=_S3_ENDPOINT,
    aws_access_key_id=_S3_KEY,
    aws_secret_access_key=_S3_SECRET,
    config=Config(
        connect_timeout=5,
        read_timeout=10,
        retries={"max_attempts": 2, "mode": "standard"},
    ),
)


def _ensure_bucket() -> None:
    try:
        _s3.head_bucket(Bucket=_BUCKET)
    except ClientError:
        _s3.create_bucket(Bucket=_BUCKET)


def _upload_sync(local_path: str, key: str) -> str:
    _ensure_bucket()
    _s3.upload_file(local_path, _BUCKET, key)
    # Persist only the object key. URLs are signed at read time by the API.
    return key


async def store_clip(frame_path: str, event_id: UUID) -> str | None:
    """Upload frame JPEG and return its private object key."""
    try:
        path = Path(frame_path).resolve()
        path.relative_to(_FRAME_ROOT)
    except (OSError, ValueError):
        log.warning("rejected clip path outside frame store")
        return None
    if not path.exists():
        return None
    key = f"clips/{event_id}.jpg"
    try:
        url = await asyncio.get_event_loop().run_in_executor(
            None, _upload_sync, frame_path, key
        )
        return url
    except (BotoCoreError, ClientError, OSError) as exc:
        log.warning(
            "clip upload failed for event %s (%s)", event_id, type(exc).__name__
        )
        return None


async def persist_event(conn: asyncpg.Connection, event: Event) -> None:
    embedding = await _get_embedding(event)

    await conn.execute(
        """
        INSERT INTO events
            (id, camera_id, event_type, timestamp, person_id, object_id,
             location_label, action_label, confidence, metadata,
             clip_path, embedding)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
        ON CONFLICT DO NOTHING
        """,
        event.id,
        event.camera_id,
        event.event_type.value,
        event.timestamp,
        event.person_id,
        event.object_id,
        event.location_label,
        event.action_label,
        event.confidence,
        event.metadata,
        event.clip_path,
        embedding,
    )


async def purge_expired_events(conn: asyncpg.Connection) -> int:
    """Delete expired event rows and their private clip objects."""
    rows = await conn.fetch(
        """
        SELECT e.id, e.clip_path
        FROM events e
        JOIN cameras c ON e.camera_id = c.id
        WHERE
          e.timestamp < NOW() - make_interval(days => COALESCE(
              (SELECT p.retention_days FROM persons p WHERE p.id = e.person_id),
              $1
          ))
        LIMIT 1000
        """,
        _DEFAULT_RETENTION_DAYS,
    )
    deletable_ids = []
    keys_by_id: dict[UUID, str] = {}
    for row in rows:
        if not row["clip_path"]:
            deletable_ids.append(row["id"])
            continue
        try:
            key = object_key(row["clip_path"])
        except ValueError:
            log.warning("skipping invalid expired clip key")
            # The value cannot identify a safe object; remove the event so a
            # malformed legacy key cannot block retention forever.
            deletable_ids.append(row["id"])
            continue
        keys_by_id[row["id"]] = key

    if keys_by_id:
        try:
            await asyncio.get_running_loop().run_in_executor(
                None, _delete_objects_sync, list(keys_by_id.values())
            )
        except (BotoCoreError, ClientError, OSError, RuntimeError) as exc:
            log.warning(
                "retention clip cleanup failed; preserving %d event rows (%s)",
                len(keys_by_id),
                type(exc).__name__,
            )
        else:
            deletable_ids.extend(keys_by_id)

    if not deletable_ids:
        return 0
    async with conn.transaction():
        # alert_deliveries intentionally has no FK to the hypertable's
        # composite primary key, so retention must remove its history
        # explicitly before deleting the corresponding events.
        await conn.execute(
            "DELETE FROM alert_deliveries WHERE event_id = ANY($1::uuid[])",
            deletable_ids,
        )
        await conn.execute(
            "DELETE FROM events WHERE id = ANY($1::uuid[])",
            deletable_ids,
        )
    return len(deletable_ids)


async def purge_expired_detections(conn: asyncpg.Connection) -> int:
    """Delete one bounded batch of raw detections beyond retention."""
    result = await conn.execute(
        """
        WITH expired AS (
            SELECT d.id, d.timestamp
            FROM detections d
            JOIN cameras c ON c.id = d.camera_id
            WHERE d.timestamp < NOW() - make_interval(days => COALESCE(
                (SELECT p.retention_days
                 FROM persons p
                 WHERE p.id = d.person_id),
                $1
            ))
            ORDER BY d.timestamp, d.id
            LIMIT 5000
        )
        DELETE FROM detections d
        USING expired
        WHERE d.id = expired.id AND d.timestamp = expired.timestamp
        """,
        _DEFAULT_RETENTION_DAYS,
    )
    try:
        return int(result.rsplit(" ", 1)[-1])
    except (AttributeError, ValueError) as exc:
        raise RuntimeError("database returned an invalid detection delete count") from exc


def _delete_objects_sync(keys: list[str]) -> None:
    for start in range(0, len(keys), 1000):
        response = _s3.delete_objects(
            Bucket=_BUCKET,
            Delete={"Objects": [{"Key": key} for key in keys[start:start + 1000]]},
        )
        errors = response.get("Errors", [])
        if errors:
            raise RuntimeError(f"object storage rejected {len(errors)} deletions")


async def _get_embedding(event: Event) -> str | None:
    text = event.to_text()
    try:
        async with httpx.AsyncClient(
            timeout=3.0, follow_redirects=False
        ) as client:
            resp = await client.post(
                f"{_QUERY_ENGINE}/embed", json={"text": text}
            )
            resp.raise_for_status()
            vec = resp.json()["embedding"]
            if (
                not isinstance(vec, list)
                or len(vec) != 384
                or not all(
                    isinstance(value, (int, float)) and math.isfinite(value)
                    for value in vec
                )
            ):
                raise ValueError("embedding must contain 384 finite numbers")
            return "[" + ",".join(f"{v:.6f}" for v in vec) + "]"
    except (httpx.HTTPError, KeyError, TypeError, ValueError, RuntimeError) as exc:
        log.warning(
            "embedding skipped for event %s (%s)", event.id, type(exc).__name__
        )
        return None
