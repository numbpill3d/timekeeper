"""Shared time-zone behavior tests."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import omniscient_shared.time as time_utils
from omniscient_shared.models.entity import DetectionMessage, FrameMessage
from omniscient_shared.models.event import Event, EventType


def test_to_local_converts_aware_timestamp(monkeypatch):
    monkeypatch.setattr(time_utils, "LOCAL_TIMEZONE", ZoneInfo("America/New_York"))
    converted = time_utils.to_local(datetime(2026, 7, 1, 16, 30, tzinfo=UTC))
    assert converted.hour == 12
    assert converted.tzinfo == ZoneInfo("America/New_York")


def test_to_local_treats_naive_timestamp_as_utc(monkeypatch):
    monkeypatch.setattr(time_utils, "LOCAL_TIMEZONE", ZoneInfo("America/New_York"))
    converted = time_utils.to_local(datetime(2026, 1, 1, 16, 30))
    assert converted.hour == 11


def test_event_and_frame_models_normalize_naive_timestamps_to_utc():
    event = Event(
        camera_id="00000000-0000-0000-0000-000000000001",
        event_type=EventType.person_entered,
        timestamp="2026-01-01T16:30:00",
        action_label="Person entered",
    )
    frame = FrameMessage(
        camera_id="00000000-0000-0000-0000-000000000001",
        timestamp="2026-01-01T16:30:00",
        frame_id="frame-1",
        frame_path="/tmp/frames/frame-1.jpg",
        width=100,
        height=100,
    )
    detection_message = DetectionMessage(
        camera_id="00000000-0000-0000-0000-000000000001",
        timestamp="2026-01-01T16:30:00",
        frame_id="frame-1",
    )

    assert event.timestamp.tzinfo == UTC
    assert frame.timestamp.tzinfo == UTC
    assert detection_message.timestamp.tzinfo == UTC


def test_event_text_includes_object_category_for_embedding_recall():
    event = Event(
        camera_id="00000000-0000-0000-0000-000000000001",
        event_type=EventType.object_picked_up,
        timestamp="2026-01-01T16:30:00Z",
        action_label="Object picked up",
        metadata={"object_category": "toolbox"},
    )

    assert "item: toolbox" in event.to_text()


def test_event_text_uses_configured_local_timezone(monkeypatch):
    monkeypatch.setattr(time_utils, "LOCAL_TIMEZONE", ZoneInfo("America/New_York"))
    event = Event(
        camera_id="00000000-0000-0000-0000-000000000001",
        event_type=EventType.person_entered,
        timestamp="2026-07-01T16:30:00Z",
        action_label="Person entered",
    )

    assert "[2026-07-01 12:30:00]" in event.to_text()
