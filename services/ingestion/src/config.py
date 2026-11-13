"""Validated ingestion configuration values."""

from __future__ import annotations

from omniscient_shared.models.camera import Camera

NORMAL_RECONNECT_DELAY_S = 1.0


def parse_frame_interval(raw: str) -> float:
    try:
        value = float(raw)
    except ValueError as exc:
        raise RuntimeError("FRAME_INTERVAL_S must be a number") from exc
    if not 0.01 <= value <= 60:
        raise RuntimeError("FRAME_INTERVAL_S must be between 0.01 and 60 seconds")
    return value


def safe_stream_error_context(camera: Camera, error: BaseException) -> str:
    """Describe a stream failure without logging URLs or provider details."""
    return f"{camera.name} ({camera.protocol.value}): {type(error).__name__}"
