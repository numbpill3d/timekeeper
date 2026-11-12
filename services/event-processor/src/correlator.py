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

        elif event.event_type == EventType.object_placed:
            match = self._find_pickup(event)
            if match:
                pickup_key, from_cam, from_evt, match_method = match
                self._pending_pickups.pop(pickup_key, None)
                if from_cam != str(event.camera_id):
                    object_name = event.metadata.get("object_category") or from_evt.metadata.get(
                        "object_category"
                    ) or from_evt.action_label.split()[0].lower()
                    label = f"{str(object_name).capitalize()} moved"
                    if from_evt.location_label:
                        label += f" from {from_evt.location_label}"
                    if event.location_label:
                        label += f" to {event.location_label}"
                    confidence = min(from_evt.confidence, event.confidence)
                    if match_method == "category_time_window":
                        confidence *= 0.75
                    extra.append(
                        Event(
                            camera_id=event.camera_id,
                            event_type=EventType.object_moved,
                            timestamp=event.timestamp,
                            object_id=event.object_id,
                            person_id=from_evt.person_id or event.person_id,
                            location_label=event.location_label,
                            action_label=label,
                            confidence=confidence,
                            metadata={
                                **event.metadata,
                                "from_camera_id": from_cam,
                                "from_location": from_evt.location_label,
                                "pickup_attribution": from_evt.metadata.get("attribution"),
                                "placement_attribution": event.metadata.get("attribution"),
                                "identity_match": match_method,
                            },
                        )
                    )
                    log.info(
                        "object_moved: %s %s->%s (%s)",
                        event.object_id,
                        from_cam,
                        event.camera_id,
                        match_method,
                    )

        return extra

    def _find_pickup(
        self, event: Event
    ) -> tuple[str, str, Event, str] | None:
        """Find an exact object match, or one unambiguous category match.

        Object track IDs are camera/session scoped, so an exact UUID cannot
        survive a camera transition. The category fallback is deliberately
        conservative: more than one candidate means the system must not claim
        which item moved.
        """
        if event.object_id:
            key = str(event.object_id)
            pickup = self._pending_pickups.get(key)
            if pickup:
                return key, pickup[0], pickup[1], "object_id"

        category = event.metadata.get("object_category")
        if not category:
            return None
        candidates = [
            (key, *pickup)
            for key, pickup in self._pending_pickups.items()
            if pickup[0] != str(event.camera_id)
            and pickup[1].metadata.get("object_category") == category
        ]
        if len(candidates) != 1:
            return None
        key, from_cam, from_evt, _ = candidates[0]
        return key, from_cam, from_evt, "category_time_window"

    def _expire(self, now: datetime) -> None:
        cutoff = now - CROSS_CAMERA_WINDOW
        self._pending_pickups = {
            k: v for k, v in self._pending_pickups.items() if v[2] >= cutoff
        }
