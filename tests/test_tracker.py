"""Tracker boundary tests for unassigned detections."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import numpy as np
import tracker as tracker_module
from tracker import (
    RawDetection,
    Tracker,
    stream_gap_requires_reset,
)


class _NoAssignmentTracker:
    def update_with_detections(self, detections):
        return SimpleNamespace(
            xyxy=np.empty((0, 4), dtype=np.float32),
            tracker_id=np.empty((0,), dtype=np.int32),
        )


class _AssignedTracker:
    def update_with_detections(self, detections):
        return SimpleNamespace(
            xyxy=np.array([[10, 10, 40, 80]], dtype=np.float32),
            tracker_id=np.array([7], dtype=np.int32),
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


def test_reset_forgets_class_trackers():
    tracker = Tracker()
    tracker._trackers["person"] = object()
    tracker._max_scoped_id = 1

    tracker.reset()

    assert tracker._trackers == {}
    assert tracker._track_id_base == 2


def test_reset_does_not_reuse_scoped_track_ids(monkeypatch):
    tracker = Tracker()
    monkeypatch.setattr(
        tracker_module,
        "sv",
        SimpleNamespace(Detections=lambda **kwargs: kwargs),
    )
    monkeypatch.setattr(tracker, "_tracker_for", lambda _class_name: _AssignedTracker())
    detection = RawDetection(
        track_id=-1,
        class_name="person",
        confidence=0.9,
        bbox=(0.1, 0.1, 0.4, 0.8),
    )

    first = tracker.update([detection], (100, 100))[0].track_id
    tracker.reset()
    second = tracker.update([detection], (100, 100))[0].track_id

    assert first != second


def test_stream_gap_requires_reset_but_malformed_timezone_does_not():
    current = datetime(2026, 1, 1, tzinfo=UTC)
    assert stream_gap_requires_reset(current, current + timedelta(seconds=6))
    assert not stream_gap_requires_reset(
        current.replace(tzinfo=None), current + timedelta(seconds=6)
    )
