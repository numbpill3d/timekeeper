"""Tracker boundary tests for unassigned detections."""

from types import SimpleNamespace

import numpy as np
import tracker as tracker_module
from tracker import RawDetection, Tracker


class _NoAssignmentTracker:
    def update_with_detections(self, detections):
        return SimpleNamespace(
            xyxy=np.empty((0, 4), dtype=np.float32),
            tracker_id=np.empty((0,), dtype=np.int32),
        )


def test_unassigned_boxes_are_not_published(monkeypatch):
    tracker = Tracker()
    monkeypatch.setattr(
        tracker_module,
        "sv",
        SimpleNamespace(Detections=lambda **kwargs: kwargs),
    )
    monkeypatch.setattr(
        tracker,
        "_tracker_for",
        lambda _class_name: _NoAssignmentTracker(),
    )

    detections = tracker.update(
        [
            RawDetection(
                track_id=-1,
                class_name="person",
                confidence=0.9,
                bbox=(0.1, 0.1, 0.4, 0.8),
            )
        ],
        (100, 100),
    )

    assert detections == []
