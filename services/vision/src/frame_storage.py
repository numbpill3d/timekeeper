"""Safe cleanup for frames dropped before the detection topic."""

from __future__ import annotations

import os
from pathlib import Path

_FRAME_ROOT = Path(os.getenv("FRAME_STORE_PATH", "/tmp/frames")).resolve()


def cleanup_unpublished_frame(frame_path: str | None) -> None:
    """Remove a frame the vision worker will not publish downstream.

    Frame paths are untrusted Kafka payloads. Cleanup is deliberately
    best-effort and can only unlink files below the configured shared root.
    Published frames remain owned by the event processor for clip extraction.
    """
    if not frame_path:
        return
    try:
        path = Path(frame_path).resolve()
        path.relative_to(_FRAME_ROOT)
        path.unlink(missing_ok=True)
    except (OSError, ValueError):
        return
