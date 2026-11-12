"""Pure helpers for validating frame and object-storage paths."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

_BUCKET = os.getenv("MEDIA_BUCKET", "omniscient-media")
_ALLOWED_HOSTS = {
    urlparse(os.getenv("S3_ENDPOINT_URL", "http://minio:9000")).hostname,
    urlparse(os.getenv("S3_PUBLIC_ENDPOINT_URL", "")).hostname,
}


def object_key(value: str) -> str:
    """Normalize a stored key while rejecting foreign URLs and traversal."""
    parsed = urlparse(value)
    prefix = f"/{_BUCKET}/"
    if (
        parsed.scheme
        and parsed.netloc
        and parsed.hostname in _ALLOWED_HOSTS
        and parsed.path.startswith(prefix)
    ):
        key = parsed.path[len(prefix):]
    elif parsed.scheme and parsed.netloc:
        raise ValueError("clip URL does not belong to the configured bucket")
    else:
        key = value.lstrip("/")
    if not key or ".." in Path(key).parts or "\\" in key:
        raise ValueError("invalid clip object key")
    return key
