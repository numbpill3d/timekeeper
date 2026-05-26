"""
ByteTrack multi-object tracker via the supervision library.

Assigns persistent track IDs across frames so that a person or
object retains identity even through brief occlusions.
"""

from __future__ import annotations

import numpy as np
import supervision as sv

from .detector import RawDetection


class Tracker:
    def __init__(
        self,
        track_activation_threshold: float = 0.25,
        lost_track_buffer: int = 30,
        minimum_matching_threshold: float = 0.8,
        frame_rate: int = 30,
    ) -> None:
        self._bt = sv.ByteTracker(
            track_activation_threshold=track_activation_threshold,
            lost_track_buffer=lost_track_buffer,
            minimum_matching_threshold=minimum_matching_threshold,
            frame_rate=frame_rate,
        )

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

        # Denormalize to pixel coords for ByteTrack
        xyxy = np.array(
            [
                [d.bbox[0] * w, d.bbox[1] * h, d.bbox[2] * w, d.bbox[3] * h]
                for d in detections
            ],
            dtype=np.float32,
        )
        confs = np.array([d.confidence for d in detections], dtype=np.float32)
        class_ids = np.zeros(len(detections), dtype=int)

        sv_dets = sv.Detections(
            xyxy=xyxy,
            confidence=confs,
            class_id=class_ids,
        )
        tracked = self._bt.update_with_detections(sv_dets)

        # Map tracker IDs back to detections by bbox overlap
        updated: list[RawDetection] = list(detections)
        if tracked.tracker_id is not None:
            for i, det in enumerate(updated):
                if i < len(tracked.tracker_id):
                    tid = tracked.tracker_id[i]
                    updated[i] = RawDetection(
                        track_id=int(tid) if tid is not None else -1,
                        class_name=det.class_name,
                        confidence=det.confidence,
                        bbox=det.bbox,
                    )

        return updated
