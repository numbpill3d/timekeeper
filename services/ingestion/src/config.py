"""Validated ingestion configuration values."""

from __future__ import annotations


def parse_frame_interval(raw: str) -> float:
    try:
        value = float(raw)
    except ValueError as exc:
        raise RuntimeError("FRAME_INTERVAL_S must be a number") from exc
    if not 0.01 <= value <= 60:
        raise RuntimeError("FRAME_INTERVAL_S must be between 0.01 and 60 seconds")
    return value
