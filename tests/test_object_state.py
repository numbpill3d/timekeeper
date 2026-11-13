from datetime import UTC, datetime, timedelta
from uuid import uuid4

from object_state import OBJECT_TRACK_TTL, prune_stale_object_tracks


def test_prune_stale_object_tracks_keeps_recent_and_other_camera_entries():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    recent = "camera-a:recent:person"
    stale = "camera-a:stale:person"
    other = "camera-b:stale:person"
    object_map = {key: uuid4() for key in (recent, stale, other)}
    last_seen = {
        recent: now - OBJECT_TRACK_TTL + timedelta(seconds=1),
        stale: now - OBJECT_TRACK_TTL - timedelta(seconds=1),
        other: now - OBJECT_TRACK_TTL - timedelta(seconds=1),
    }

    prune_stale_object_tracks(object_map, last_seen, "camera-a", now)

    assert recent in object_map and recent in last_seen
    assert stale not in object_map and stale not in last_seen
    assert other in object_map and other in last_seen


def test_prune_stale_object_tracks_handles_missing_timestamp_entries():
    object_map = {"camera-a:orphan:object": uuid4()}
    last_seen: dict[str, datetime] = {}

    prune_stale_object_tracks(
        object_map, last_seen, "camera-a", datetime.now(UTC)
    )

    assert object_map
