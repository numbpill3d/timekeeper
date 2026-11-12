"""Unit tests for CameraAggregator single-camera event detection."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from omniscient_shared.models.entity import Detection, DetectionMessage
from omniscient_shared.models.event import EventType
from aggregator import EXIT_TIMEOUT, CameraAggregator


_CAM = uuid4()


def _det(
    class_name: str = "person",
    track_id: int = 1,
    ts: datetime | None = None,
) -> Detection:
    return Detection(
        camera_id=_CAM,
        timestamp=ts or datetime.now(tz=timezone.utc),
        frame_id="f1",
        track_id=track_id,
        class_name=class_name,
        confidence=0.95,
        bbox=(0.1, 0.1, 0.5, 0.8),
    )


def test_object_events_preserve_person_attribution():
    person_id = uuid4()
    agg = CameraAggregator(camera_id=str(_CAM), location_label="kitchen")
    detection = _det("keys", track_id=3)
    detection.person_id = person_id
    detection.association_confidence = 0.87
    detection.association_method = "person_object_proximity"

    events = agg.process(_msg([detection]))
    event = next(e for e in events if e.event_type == EventType.object_placed)
    assert event.person_id == person_id
    assert event.metadata["attribution"]["confidence"] == 0.87


def test_object_pickup_event_preserves_person_attribution():
    person_id = uuid4()
    agg = CameraAggregator(camera_id=str(_CAM), location_label="kitchen")
    t = datetime.now(tz=timezone.utc)
    detection = _det("keys", track_id=3, ts=t)
    detection.person_id = person_id
    agg.process(_msg([detection], ts=t))
    events = agg.process(_msg([], ts=t + EXIT_TIMEOUT + timedelta(seconds=1)))
    event = next(e for e in events if e.event_type == EventType.object_picked_up)
    assert event.person_id == person_id


def _msg(dets: list[Detection], ts: datetime | None = None) -> DetectionMessage:
    return DetectionMessage(
        camera_id=_CAM,
        timestamp=ts or datetime.now(tz=timezone.utc),
        frame_id="f1",
        frame_path="/tmp/f1.jpg",
        detections=dets,
    )


def test_person_entered_on_first_detection():
    agg = CameraAggregator(camera_id=str(_CAM), location_label=None)
    events = agg.process(_msg([_det("person", track_id=1)]))
    assert len(events) == 1
    assert events[0].event_type == EventType.person_entered


def test_no_repeated_entered_event():
    agg = CameraAggregator(camera_id=str(_CAM), location_label=None)
    t = datetime.now(tz=timezone.utc)
    agg.process(_msg([_det("person", track_id=1)], ts=t))
    events = agg.process(
        _msg([_det("person", track_id=1)], ts=t + timedelta(seconds=1))
    )
    assert events == []


def test_person_exited_after_timeout():
    agg = CameraAggregator(camera_id=str(_CAM), location_label=None)
    t = datetime.now(tz=timezone.utc)
    agg.process(_msg([_det("person", track_id=1)], ts=t))
    events = agg.process(
        _msg([], ts=t + EXIT_TIMEOUT + timedelta(seconds=1))
    )
    assert any(e.event_type == EventType.person_exited for e in events)


def test_person_not_exited_before_timeout():
    agg = CameraAggregator(camera_id=str(_CAM), location_label=None)
    t = datetime.now(tz=timezone.utc)
    agg.process(_msg([_det("person", track_id=1)], ts=t))
    events = agg.process(_msg([], ts=t + timedelta(seconds=1)))
    assert not any(e.event_type == EventType.person_exited for e in events)


def test_package_delivered_at_entrance_camera():
    agg = CameraAggregator(camera_id=str(_CAM), location_label="front entrance")
    events = agg.process(_msg([_det("package", track_id=5)]))
    assert any(e.event_type == EventType.package_delivered for e in events)


def test_package_not_delivered_non_entrance():
    agg = CameraAggregator(camera_id=str(_CAM), location_label="kitchen")
    events = agg.process(_msg([_det("package", track_id=5)]))
    assert not any(e.event_type == EventType.package_delivered for e in events)
    assert any(e.event_type == EventType.object_placed for e in events)


def test_object_placed_on_first_non_person():
    agg = CameraAggregator(camera_id=str(_CAM), location_label=None)
    events = agg.process(_msg([_det("keys", track_id=3)]))
    assert any(e.event_type == EventType.object_placed for e in events)


def test_multiple_tracks_emit_independent_entered_events():
    agg = CameraAggregator(camera_id=str(_CAM), location_label=None)
    t = datetime.now(tz=timezone.utc)
    events = agg.process(
        _msg([_det("person", track_id=1), _det("person", track_id=2)], ts=t)
    )
    entered = [e for e in events if e.event_type == EventType.person_entered]
    assert len(entered) == 2


def test_person_and_object_can_share_tracker_id_without_state_collision():
    agg = CameraAggregator(camera_id=str(_CAM), location_label=None)
    t = datetime.now(tz=timezone.utc)
    events = agg.process(
        _msg(
            [_det("person", track_id=1, ts=t), _det("keys", track_id=1, ts=t)],
            ts=t,
        )
    )
    assert {event.event_type for event in events} == {
        EventType.person_entered,
        EventType.object_placed,
    }

    later = t + EXIT_TIMEOUT + timedelta(seconds=1)
    events = agg.process(_msg([], ts=later))
    assert {event.event_type for event in events} == {
        EventType.person_exited,
        EventType.object_picked_up,
    }
