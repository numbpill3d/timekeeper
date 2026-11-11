"""Private object-storage helpers for short-lived evidence URLs."""

from __future__ import annotations

import os
from urllib.parse import urlparse

import boto3

_PUBLIC_ENDPOINT = os.getenv(
    "S3_PUBLIC_ENDPOINT_URL", os.getenv("S3_ENDPOINT_URL", "http://minio:9000")
)
_KEY = os.getenv("S3_ACCESS_KEY", "minioadmin")
_SECRET = os.getenv("S3_SECRET_KEY", "minioadmin")
_BUCKET = os.getenv("MEDIA_BUCKET", "omniscient-media")
_TTL = max(60, int(os.getenv("CLIP_URL_TTL_SECONDS", "300")))


def _client():
    return boto3.client(
        "s3",
        endpoint_url=_PUBLIC_ENDPOINT,
        aws_access_key_id=_KEY,
        aws_secret_access_key=_SECRET,
    )


def object_key(value: str | None) -> str | None:
    """Normalize current keys and legacy internal bucket URLs."""
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        prefix = f"/{_BUCKET}/"
        if parsed.path.startswith(prefix):
            return parsed.path[len(prefix):]
    return value.lstrip("/")


def signed_clip_url(value: str | None) -> str | None:
    key = object_key(value)
    if not key:
        return None
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": _BUCKET, "Key": key},
        ExpiresIn=_TTL,
    )
