"""
Cross-camera event correlator.

Watches for objects that are picked up on one camera and placed on
another within CROSS_CAMERA_WINDOW seconds, emitting object_moved events
to link the two detections into a single coherent activity record.

Person cross-camera tracking is handled implicitly: the ReID model in
the vision service assigns the same person_id across cameras, so the
aggregator already emits person_entered/exited with stable identity.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from omniscient_shared.models.event import Event, EventType

log = logging.getLogger(__name__)

CROSS_CAMERA_WINDOW = timedelta(seconds=30)


class Correlator:
    def __init__(self) -> None:
        # object_id -> (from_camera_id, pickup_event, pickup_time)
        self._pending_pickups: dict[str, tuple[str, Event, datetime]] = {}

    def process(self, event: Event) -> list[Event]:
        """Check if event completes a cross-camera pair. Returns any extra events."""
        self._expire(event.timestamp)
        extra: list[Event] = []

        if event.event_type == EventType.object_picked_up and event.object_id:
            oid = str(event.object_id)
            self._pending_pickups[oid] = (str(event.camera_id), event, event.timestamp)

        elif event.event_type == EventType.object_placed and event.object_id:
            oid = str(event.object_id)
            if oid in self._pending_pickups:
                from_cam, from_evt, _ = self._pending_pickups.pop(oid)
                if from_cam != str(event.camera_id):
                    obj_name = from_evt.action_label.split()[0].lower()
                    label = f"{obj_name.capitalize()} moved"
                    if from_evt.location_label:
                        label += f" from {from_evt.location_label}"
                    if event.location_label:
                        label += f" to {event.location_label}"
                    extra.append(
                        Event(
                            camera_id=event.camera_id,
                            event_type=EventType.object_moved,
                            timestamp=event.timestamp,
                            object_id=event.object_id,
                            person_id=event.person_id,
                            location_label=event.location_label,
                            action_label=label,
                            confidence=min(from_evt.confidence, event.confidence),
                            metadata={
                                **event.metadata,
                                "from_camera_id": from_cam,
                                "from_location": from_evt.location_label,
                            },
                        )
                    )
                    log.info("object_moved: %s %s->%s", oid, from_cam, event.camera_id)

        return extra

    def _expire(self, now: datetime) -> None:
        cutoff = now - CROSS_CAMERA_WINDOW
        self._pending_pickups = {
            k: v for k, v in self._pending_pickups.items() if v[2] >= cutoff
        }
