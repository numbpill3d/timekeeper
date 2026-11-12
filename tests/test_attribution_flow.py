"""End-to-end synthetic attribution flow from detection to answer wording."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from aggregator import CameraAggregator, EXIT_TIMEOUT, STILL_TIMEOUT
from llm import _format_evidence_response
from omniscient_shared.models.entity import Detection, DetectionMessage
from omniscient_shared.models.event import EventType


def test_named_person_item_pickup_survives_event_pipeline():
    camera_id = uuid4()
    person_id = uuid4()
    object_id = uuid4()
    timestamp = datetime(2026, 11, 11, 16, 30, tzinfo=timezone.utc)
    detection = Detection(
        camera_id=camera_id,
        timestamp=timestamp,
        frame_id="frame-1",
        track_id=7,
        class_name="keys",
        confidence=0.94,
        bbox=(0.42, 0.58, 0.50, 0.68),
        person_id=person_id,
        object_id=object_id,
        association_confidence=0.88,
        association_method="person_object_proximity",
    )
    aggregator = CameraAggregator(str(camera_id), "kitchen")
    aggregator.process(
        DetectionMessage(
            camera_id=camera_id,
            timestamp=timestamp,
            frame_id="frame-1",
            detections=[detection],
        )
    )
    aggregator.process(
        DetectionMessage(
            camera_id=camera_id,
            timestamp=timestamp + STILL_TIMEOUT,
            frame_id="frame-1b",
            detections=[detection.model_copy(update={"timestamp": timestamp + STILL_TIMEOUT})],
        )
    )
    events = aggregator.process(
        DetectionMessage(
            camera_id=camera_id,
            timestamp=timestamp + STILL_TIMEOUT + EXIT_TIMEOUT + timedelta(seconds=1),
            frame_id="frame-2",
            detections=[],
        )
    )
    pickup = next(e for e in events if e.event_type == EventType.object_picked_up)
    assert pickup.person_id == person_id
    assert pickup.object_id == object_id
    assert pickup.metadata["attribution"]["method"] == "person_object_proximity"

    answer = _format_evidence_response([{
        "event_type": pickup.event_type.value,
        "timestamp": pickup.timestamp,
        "person_label": "John",
        "object_category": "keys",
        "location_label": pickup.location_label,
    }])
    assert "John picked up keys" in answer
    assert "kitchen" in answer
