"""
Converts raw per-frame detections into semantic activity events.

Rules (Phase 1):
  - person_entered:  person track_id first seen this session on this camera
  - person_exited:   track_id disappeared for > EXIT_TIMEOUT seconds
  - object_moved:    tracked object's camera_id changed between detections
  - object_placed:   object track that was moving is now stationary > STILL_TIMEOUT
  - object_last_seen: stationary object track disappeared without attribution
  - object_picked_up: inferred from disappearance with person attribution
  - package_delivered: 'package' class detected near entrance camera for first time

Cross-camera correlation lives in correlator.py; this file handles
single-camera temporal aggregation only.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from uuid import NAMESPACE_URL, UUID, uuid5

from omniscient_shared.models.entity import Detection, DetectionMessage
from omniscient_shared.models.event import Event, EventType

log = logging.getLogger(__name__)

EXIT_TIMEOUT = timedelta(seconds=5)
STILL_TIMEOUT = timedelta(seconds=3)
STATIONARY_IOU_THRESHOLD = 0.6

_ENTRANCE_KEYWORDS = frozenset({"front", "entrance", "door", "entry", "porch", "foyer"})


class CameraAggregator:
    """Stateful aggregator for one camera stream."""

    def __init__(self, camera_id: str, location_label: str | None) -> None:
        self.camera_id = camera_id
        self.location_label = location_label
        # (class_name, track_id) -> state. Track IDs are only unique within a
        # tracker stream and can overlap between person/object classes.
        self._active: dict[tuple[str, int], Detection] = {}
        self._first_seen: dict[tuple[str, int], datetime] = {}
        self._last_seen: dict[tuple[str, int], datetime] = {}
        self._stationary: set[tuple[str, int]] = set()

    def process(self, msg: DetectionMessage) -> list[Event]:
        events: list[Event] = []
        now = msg.timestamp
        seen_ids: set[tuple[str, int]] = set()

        for det in msg.detections:
            key = (det.class_name, det.track_id)
            seen_ids.add(key)

            if key not in self._active:
                evt = self._on_first_seen(det, now)
                if evt:
                    events.append(evt)
                self._first_seen[key] = now
            elif det.class_name != "person":
                previous = self._active[key]
                if self._bbox_iou(previous.bbox, det.bbox) < STATIONARY_IOU_THRESHOLD:
                    # A previously stationary item has started moving again.
                    # Reset the dwell timer so a later placement is emitted
                    # after it settles at its new location.
                    self._first_seen[key] = now
                    self._stationary.discard(key)
                elif key not in self._stationary and now - self._first_seen[key] >= STILL_TIMEOUT:
                    events.append(self._on_stationary(det, now))
                    self._stationary.add(key)

            self._active[key] = det
            self._last_seen[key] = now

        # Check for exits
        stale = [
            key for key, last in self._last_seen.items()
            if key not in seen_ids and now - last > EXIT_TIMEOUT
        ]
        for key in stale:
            evt = (
                self._on_exit(self._active[key], now, msg.frame_id)
                if key[0] == "person" or key in self._stationary
                else None
            )
            if evt:
                events.append(evt)
            del self._active[key]
            del self._last_seen[key]
            self._first_seen.pop(key, None)
            self._stationary.discard(key)

        return events

    def _is_entrance(self) -> bool:
        if not self.location_label:
            return False
        loc = self.location_label.lower()
        return any(kw in loc for kw in _ENTRANCE_KEYWORDS)

    def _on_first_seen(
        self, det: Detection, now: datetime
    ) -> Event | None:
        if det.class_name == "person":
            loc_suffix = f" {self.location_label}" if self.location_label else ""
            label = f"Person entered{loc_suffix}"
            return Event(
                id=self._event_id(det, EventType.person_entered, det.frame_id),
                camera_id=det.camera_id,
                event_type=EventType.person_entered,
                timestamp=now,
                person_id=det.person_id,
                location_label=self.location_label,
                action_label=label,
                confidence=det.confidence,
            )
        if det.class_name == "package" and self._is_entrance():
            return Event(
                id=self._event_id(det, EventType.package_delivered, det.frame_id),
                camera_id=det.camera_id,
                event_type=EventType.package_delivered,
                timestamp=now,
                object_id=det.object_id,
                person_id=det.person_id,
                location_label=self.location_label,
                action_label="Package delivered"
                + (f" at {self.location_label}" if self.location_label else ""),
                confidence=self._event_confidence(det),
                metadata=self._attribution_metadata(det),
            )
        # A first sighting is not enough evidence that an object was placed;
        # wait for the stationary transition before emitting that event.
        return None

    def _on_exit(self, det: Detection, now: datetime, frame_id: str) -> Event | None:
        if det.class_name == "person":
            return Event(
                id=self._event_id(det, EventType.person_exited, frame_id),
                camera_id=det.camera_id,
                event_type=EventType.person_exited,
                timestamp=now,
                person_id=det.person_id,
                location_label=self.location_label,
                action_label=(
                    "Person left"
                    + (f" {self.location_label}" if self.location_label else "")
                ),
                confidence=det.confidence,
            )
        metadata = {
            **self._attribution_metadata(det),
            "before_frame_id": det.frame_id,
            "last_seen_at": det.timestamp.isoformat(),
        }
        if det.person_id:
            event_type = EventType.object_picked_up
            label = f"Possible pickup of {det.class_name}"
            metadata["inference"] = "possible_pickup"
        else:
            event_type = EventType.object_last_seen
            label = f"{det.class_name.capitalize()} last seen"
        return Event(
            id=self._event_id(det, event_type, frame_id),
            camera_id=det.camera_id,
            event_type=event_type,
            timestamp=now if det.person_id else det.timestamp,
            object_id=det.object_id,
            person_id=det.person_id,
            location_label=self.location_label,
            action_label=label,
            confidence=self._event_confidence(det),
            metadata=metadata,
        )

    def _on_stationary(self, det: Detection, now: datetime) -> Event:
        return Event(
            id=self._event_id(det, EventType.object_placed, det.frame_id),
            camera_id=det.camera_id,
            event_type=EventType.object_placed,
            timestamp=now,
            object_id=det.object_id,
            person_id=det.person_id,
            location_label=self.location_label,
            action_label=(
                f"{det.class_name.capitalize()} placed"
                + (f" at {self.location_label}" if self.location_label else "")
            ),
            confidence=self._event_confidence(det),
            metadata=self._attribution_metadata(det),
        )

    @staticmethod
    def _event_id(det: Detection, event_type: EventType, source_frame_id: str) -> UUID:
        """Derive an id stable across Kafka replay of one observation.

        Detection offsets are committed after event persistence.  A crash in
        between must replay safely instead of creating a second history row.
        The frame id is unique per observation, while track/object/person
        fields distinguish multiple events emitted from one frame.
        """
        source = ":".join(
            (
                str(det.camera_id),
                source_frame_id,
                event_type.value,
                str(det.track_id),
                str(det.object_id or ""),
                str(det.person_id or ""),
            )
        )
        return uuid5(NAMESPACE_URL, f"timekeeper:event:{source}")

    @staticmethod
    def _bbox_iou(
        first: tuple[float, float, float, float],
        second: tuple[float, float, float, float],
    ) -> float:
        left = max(first[0], second[0])
        top = max(first[1], second[1])
        right = min(first[2], second[2])
        bottom = min(first[3], second[3])
        intersection = max(0.0, right - left) * max(0.0, bottom - top)
        first_area = max(0.0, first[2] - first[0]) * max(0.0, first[3] - first[1])
        second_area = max(0.0, second[2] - second[0]) * max(0.0, second[3] - second[1])
        union = first_area + second_area - intersection
        return intersection / union if union else 0.0

    @staticmethod
    def _attribution_metadata(det: Detection) -> dict:
        metadata = {"object_category": det.class_name}
        if not det.person_id:
            return metadata
        metadata["attribution"] = {
            "person_id": str(det.person_id),
            "confidence": det.association_confidence,
            "method": det.association_method or "unknown",
        }
        return metadata

    @staticmethod
    def _event_confidence(det: Detection) -> float:
        if det.association_confidence is None:
            return det.confidence
        return min(det.confidence, det.association_confidence)
