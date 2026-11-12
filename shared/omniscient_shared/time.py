"""Time-zone helpers shared by query, evidence, and alert services."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _configured_timezone() -> ZoneInfo:
    name = os.getenv("TIMEZONE", "UTC").strip() or "UTC"
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise RuntimeError(f"TIMEZONE is not a valid IANA time zone: {name}") from exc


LOCAL_TIMEZONE = _configured_timezone()


def local_now() -> datetime:
    return datetime.now(tz=LOCAL_TIMEZONE)


def to_local(value: datetime) -> datetime:
    """Convert an aware timestamp to the configured display/query zone."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(LOCAL_TIMEZONE)
