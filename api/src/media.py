"""Private object-storage helpers for short-lived evidence URLs."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import PurePosixPath
from urllib.parse import urlparse

from botocore.config import Config

log = logging.getLogger(__name__)

_PUBLIC_ENDPOINT = os.getenv(
    "S3_PUBLIC_ENDPOINT_URL", os.getenv("S3_ENDPOINT_URL", "http://minio:9000")
)
_INTERNAL_ENDPOINT = os.getenv("S3_ENDPOINT_URL", _PUBLIC_ENDPOINT)
_KEY = os.getenv("S3_ACCESS_KEY", "")
_SECRET = os.getenv("S3_SECRET_KEY", "")
_BUCKET = os.getenv("MEDIA_BUCKET", "omniscient-media")
_CLIP_PREFIX = "clips/"
_TTL = max(60, int(os.getenv("CLIP_URL_TTL_SECONDS", "300")))
_S3_CONFIG = Config(
    connect_timeout=5,
    read_timeout=10,
    retries={"max_attempts": 2, "mode": "standard"},
)

if os.getenv("ENVIRONMENT", "development").lower() == "production" and (
    not _KEY or not _SECRET or _KEY == "minioadmin" or _SECRET == "minioadmin"
):
    raise RuntimeError("production media storage credentials must be configured")


def _client():
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=_PUBLIC_ENDPOINT,
        aws_access_key_id=_KEY,
        aws_secret_access_key=_SECRET,
        config=_S3_CONFIG,
    )


def _delete_keys_sync(keys: list[str]) -> None:
    import boto3

    client = boto3.client(
        "s3",
        endpoint_url=_INTERNAL_ENDPOINT,
        aws_access_key_id=_KEY,
        aws_secret_access_key=_SECRET,
        config=_S3_CONFIG,
    )
    for start in range(0, len(keys), 1000):
        response = client.delete_objects(
            Bucket=_BUCKET,
            Delete={"Objects": [{"Key": key} for key in keys[start:start + 1000]]},
        )
        errors = response.get("Errors", [])
        if errors:
            raise RuntimeError(f"object storage rejected {len(errors)} deletions")


async def delete_clip_objects(values: list[str | None]) -> None:
    """Best-effort removal of private clip objects after DB deletion."""
    keys: list[str] = []
    for value in values:
        if not value:
            continue
        try:
            key = object_key(value)
        except ValueError:
            log.warning("skipping invalid clip key during camera removal")
            continue
        if key not in keys:
            keys.append(key)
    if not keys:
        return
    try:
        await asyncio.to_thread(_delete_keys_sync, keys)
    except Exception as exc:  # noqa: BLE001 - storage SDK failures are non-fatal
        # The database deletion is already committed. Surface the orphan for
        # operators to clean up without turning a completed DB delete into a
        # misleading API failure.
        log.error(
            "camera clip cleanup failed for %d objects (%s)",
            len(keys),
            type(exc).__name__,
        )


def object_key(value: str | None) -> str | None:
    """Normalize current keys and legacy internal bucket URLs."""
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        prefix = f"/{_BUCKET}/"
        allowed_hosts = {
            urlparse(_PUBLIC_ENDPOINT).hostname,
            urlparse(_INTERNAL_ENDPOINT).hostname,
        }
        if parsed.hostname in allowed_hosts and parsed.path.startswith(prefix):
            return parsed.path[len(prefix):]
        raise ValueError("media URL does not belong to the configured bucket")
    key = value.lstrip("/")
    path = PurePosixPath(key)
    if (
        not key
        or not key.startswith(_CLIP_PREFIX)
        or ".." in path.parts
        or "\\" in key
    ):
        raise ValueError("invalid media object key")
    return key


def signed_clip_url(value: str | None) -> str | None:
    key = object_key(value)
    if not key:
        return None
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": _BUCKET, "Key": key},
        ExpiresIn=_TTL,
    )


def safe_signed_clip_url(value: str | None) -> str | None:
    """Return a clip URL when storage accepts the key; otherwise omit it."""
    try:
        return signed_clip_url(value)
    except Exception:  # noqa: BLE001 - storage SDK failures are non-fatal
        return None
