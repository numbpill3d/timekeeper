"""Bounded state helpers for session-scoped object tracking."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

OBJECT_TRACK_TTL = timedelta(seconds=10)


def prune_stale_object_tracks(
    object_map: dict[str, UUID],
    last_seen: dict[str, datetime],
    camera_id: str,
    now: datetime,
) -> None:
    """Drop object mappings absent long enough to be a new tracker session.

    ByteTrack can allocate fresh IDs as objects leave and re-enter a camera.
    Keeping every historical session ID forever grows memory and can reuse a
    stale database identity if a tracker later recycles a numeric ID. The TTL
    exceeds the event processor's disappearance timeout while retaining brief
    occlusion continuity.
    """
    prefix = f"{camera_id}:"
    cutoff = now - OBJECT_TRACK_TTL
    for key, seen_at in list(last_seen.items()):
        if key.startswith(prefix) and seen_at < cutoff:
            last_seen.pop(key, None)
            object_map.pop(key, None)
