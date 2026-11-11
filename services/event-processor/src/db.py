"""
Persist events to TimescaleDB and embed them for RAG via the query engine.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from uuid import UUID

import asyncpg
import boto3
import httpx
from botocore.exceptions import BotoCoreError, ClientError

from omniscient_shared.models.event import Event

log = logging.getLogger(__name__)

_DB_URL = os.getenv("DATABASE_URL", "")
_QUERY_ENGINE = os.getenv("QUERY_ENGINE_URL", "http://query-engine:8001")
_S3_ENDPOINT = os.getenv("S3_ENDPOINT_URL", "http://minio:9000")
_S3_KEY = os.getenv("S3_ACCESS_KEY", "minioadmin")
_S3_SECRET = os.getenv("S3_SECRET_KEY", "minioadmin")
_BUCKET = os.getenv("MEDIA_BUCKET", "omniscient-media")

_s3 = boto3.client(
    "s3",
    endpoint_url=_S3_ENDPOINT,
    aws_access_key_id=_S3_KEY,
    aws_secret_access_key=_S3_SECRET,
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
    path = Path(frame_path)
    if not path.exists():
        return None
    key = f"clips/{event_id}.jpg"
    try:
        url = await asyncio.get_event_loop().run_in_executor(
            None, _upload_sync, frame_path, key
        )
        return url
    except (BotoCoreError, ClientError, OSError) as exc:
        log.warning("clip upload failed for event %s: %s", event_id, exc)
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


async def _get_embedding(event: Event) -> str | None:
    text = event.to_text()
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.post(
                f"{_QUERY_ENGINE}/embed", json={"text": text}
            )
            resp.raise_for_status()
            vec = resp.json()["embedding"]
            return "[" + ",".join(f"{v:.6f}" for v in vec) + "]"
    except Exception as exc:
        log.warning("embedding skipped for event %s: %s", event.id, exc)
        return None
