"""
ByteTrack multi-object tracker via the supervision library.

Assigns persistent track IDs across frames so that a person or
object retains identity even through brief occlusions.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

try:
    import supervision as sv
except ImportError:  # Keep the lightweight tracking contract importable in CI.
    sv = None


@dataclass
class RawDetection:
    track_id: int
    class_name: str
    confidence: float
    bbox: tuple[float, float, float, float]


class Tracker:
    def __init__(
        self,
        track_activation_threshold: float = 0.25,
        lost_track_buffer: int = 30,
        minimum_matching_threshold: float = 0.8,
        frame_rate: int = 30,
    ) -> None:
        self._tracker_config = {
            "track_activation_threshold": track_activation_threshold,
            "lost_track_buffer": lost_track_buffer,
            "minimum_matching_threshold": minimum_matching_threshold,
            "frame_rate": frame_rate,
        }
        # ByteTrack should never match a person box to an object box. Keeping
        # one stateful tracker per class preserves IDs while preventing
        # cross-class identity swaps.
        self._trackers: dict[str, sv.ByteTrack] = {}

    def _tracker_for(self, class_name: str) -> sv.ByteTrack:
        if sv is None:
            raise RuntimeError("vision tracking requires the supervision package")
        if class_name not in self._trackers:
            self._trackers[class_name] = sv.ByteTrack(**self._tracker_config)
        return self._trackers[class_name]

    def update(
        self,
        detections: list[RawDetection],
        frame_shape: tuple[int, int],
    ) -> list[RawDetection]:
        """Assign/update track IDs for a batch of detections.

        frame_shape: (height, width) — needed to denormalize bbox for ByteTrack.
        Returns the same detections with track_id fields populated.
        """
        if not detections:
            return []

        h, w = frame_shape

        updated: list[RawDetection] = list(detections)
        by_class: dict[str, list[int]] = {}
        for index, detection in enumerate(detections):
            by_class.setdefault(detection.class_name, []).append(index)

        for class_name, indices in by_class.items():
            xyxy = np.array(
                [
                    [
                        detections[index].bbox[0] * w,
                        detections[index].bbox[1] * h,
                        detections[index].bbox[2] * w,
                        detections[index].bbox[3] * h,
                    ]
                    for index in indices
                ],
                dtype=np.float32,
            )
            confs = np.array(
                [detections[index].confidence for index in indices],
                dtype=np.float32,
            )
            tracked = self._tracker_for(class_name).update_with_detections(
                sv.Detections(xyxy=xyxy, confidence=confs)
            )
            if tracked.tracker_id is None:
                continue

            # ByteTrack may filter and reorder detections. Match its output
            # boxes back to source detections instead of assuming positions
            # remain stable after a dropout.
            used: set[int] = set()
            for tracked_box, tid in zip(tracked.xyxy, tracked.tracker_id):
                if tid is None:
                    continue
                best_index, _ = max(
                    (
                        (local, _iou(tracked_box, xyxy[local]))
                        for local in range(len(indices))
                        if local not in used
                    ),
                    key=lambda pair: pair[1],
                    default=(-1, 0.0),
                )
                if best_index < 0:
                    continue
                used.add(best_index)
                source_index = indices[best_index]
                det = updated[source_index]
                updated[source_index] = RawDetection(
                    track_id=int(tid),
                    class_name=det.class_name,
                    confidence=det.confidence,
                    bbox=det.bbox,
                )

        # A detector box without a ByteTrack assignment is not safe to emit:
        # downstream aggregation treats track IDs as stable identities. Drop
        # those boxes instead of publishing the sentinel -1.
        return [detection for detection in updated if detection.track_id >= 0]


def _iou(left: np.ndarray, right: np.ndarray) -> float:
    """Return intersection-over-union for two ``xyxy`` boxes."""
    x1 = max(float(left[0]), float(right[0]))
    y1 = max(float(left[1]), float(right[1]))
    x2 = min(float(left[2]), float(right[2]))
    y2 = min(float(left[3]), float(right[3]))
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    left_area = max(0.0, float(left[2]) - float(left[0])) * max(
        0.0, float(left[3]) - float(left[1])
    )
    right_area = max(0.0, float(right[2]) - float(right[0])) * max(
        0.0, float(right[3]) - float(right[1])
    )
    union = left_area + right_area - intersection
    return intersection / union if union else 0.0
