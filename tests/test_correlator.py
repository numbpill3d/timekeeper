"""Unit tests for cross-camera object correlation."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from correlator import CROSS_CAMERA_WINDOW, Correlator
from omniscient_shared.models.event import Event, EventType


def _event(
    event_type: EventType,
    camera_id=None,
    object_id=None,
    ts: datetime | None = None,
    location_label: str | None = None,
    category: str | None = None,
) -> Event:
    return Event(
        camera_id=camera_id or uuid4(),
        event_type=event_type,
        timestamp=ts or datetime.now(tz=UTC),
        object_id=object_id,
        location_label=location_label,
        action_label="test",
        metadata={"object_category": category} if category else {},
    )


def test_object_moved_cross_camera():
    correlator = Correlator()
    obj_id = uuid4()
    cam_a, cam_b = uuid4(), uuid4()
    t = datetime.now(tz=UTC)

    correlator.process(_event(EventType.object_picked_up, cam_a, obj_id, ts=t))
    extra = correlator.process(
        _event(EventType.object_placed, cam_b, obj_id, ts=t + timedelta(seconds=5))
    )
    assert len(extra) == 1
    assert extra[0].event_type == EventType.object_moved


def test_no_moved_event_same_camera():
    correlator = Correlator()
    obj_id = uuid4()
    cam = uuid4()
    t = datetime.now(tz=UTC)

    correlator.process(_event(EventType.object_picked_up, cam, obj_id, ts=t))
    extra = correlator.process(
        _event(EventType.object_placed, cam, obj_id, ts=t + timedelta(seconds=2))
    )
    assert extra == []


def test_pickup_expires_before_place():
    correlator = Correlator()
    obj_id = uuid4()
    cam_a, cam_b = uuid4(), uuid4()
    t = datetime.now(tz=UTC)

    correlator.process(_event(EventType.object_picked_up, cam_a, obj_id, ts=t))
    late = t + CROSS_CAMERA_WINDOW + timedelta(seconds=1)
    extra = correlator.process(
        _event(EventType.object_placed, cam_b, obj_id, ts=late)
    )
    assert extra == []


def test_different_objects_no_cross_match():
    correlator = Correlator()
    cam_a, cam_b = uuid4(), uuid4()
    t = datetime.now(tz=UTC)

    correlator.process(_event(EventType.object_picked_up, cam_a, uuid4(), ts=t))
    extra = correlator.process(
        _event(EventType.object_placed, cam_b, uuid4(), ts=t + timedelta(seconds=2))
    )
    assert extra == []


def test_unrelated_event_type_produces_no_extra():
    extra = Correlator().process(_event(EventType.person_entered))
    assert extra == []


def test_moved_event_carries_from_camera_metadata():
    correlator = Correlator()
    obj_id = uuid4()
    cam_a, cam_b = uuid4(), uuid4()
    t = datetime.now(tz=UTC)

    correlator.process(
        _event(
            EventType.object_picked_up, cam_a, obj_id,
            ts=t, location_label="kitchen",
        )
    )
    extra = correlator.process(
        _event(
            EventType.object_placed, cam_b, obj_id,
            ts=t + timedelta(seconds=3), location_label="bedroom",
        )
    )
    assert extra[0].metadata.get("from_camera_id") == str(cam_a)


def test_category_fallback_correlates_camera_scoped_object_ids():
    correlator = Correlator()
    cam_a, cam_b = uuid4(), uuid4()
    t = datetime.now(tz=UTC)

    correlator.process(
        _event(
            EventType.object_picked_up,
            cam_a,
            uuid4(),
            ts=t,
            location_label="kitchen",
            category="keys",
        )
    )
    extra = correlator.process(
        _event(
            EventType.object_placed,
            cam_b,
            uuid4(),
            ts=t + timedelta(seconds=5),
            location_label="office",
            category="keys",
        )
    )
    assert len(extra) == 1
    assert extra[0].metadata["identity_match"] == "category_time_window"
    assert extra[0].confidence < 1.0


def test_ambiguous_category_does_not_claim_a_move():
    correlator = Correlator()
    cam_a, cam_b = uuid4(), uuid4()
    t = datetime.now(tz=UTC)
    for _ in range(2):
        correlator.process(
            _event(EventType.object_picked_up, cam_a, uuid4(), ts=t, category="keys")
        )
    extra = correlator.process(
        _event(EventType.object_placed, cam_b, uuid4(), ts=t + timedelta(seconds=5), category="keys")
    )
    assert extra == []
