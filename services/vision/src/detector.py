"""
YOLOv8-based object and person detector.

Runs at 15-30 FPS on edge hardware (NVIDIA Jetson / RTX class).
Model is YOLOv8n for edge, YOLOv8m for cloud fallback.
Phase 1 tracks 10 high-value household categories + persons.
"""

from __future__ import annotations

import numpy as np
import torch
from ultralytics import YOLO

from .tracker import RawDetection

# Phase 1 category set — maps COCO class names to canonical labels
_COCO_TO_CANONICAL: dict[str, str] = {
    "person": "person",
    "cell phone": "phone",
    "laptop": "laptop",
    "backpack": "backpack",
    "handbag": "bag",
    "suitcase": "bag",
    "bottle": "bottle",
    "cup": "cup",
    "book": "book",
    "scissors": "tool",
    "dog": "dog",
    "cat": "cat",
    "car": "car",
    "bicycle": "bicycle",
}

# Custom fine-tuned classes added on top of COCO
_CUSTOM_CLASSES: set[str] = {"keys", "wallet", "medication", "package"}


class Detector:
    def __init__(
        self,
        model_path: str = "yolov8n.pt",
        device: str | None = None,
        conf_threshold: float = 0.4,
        iou_threshold: float = 0.45,
    ) -> None:
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.conf = conf_threshold
        self.iou = iou_threshold
        self.model = YOLO(model_path)
        self.model.to(self.device)

    def detect(
        self, frame: np.ndarray
    ) -> list[RawDetection]:
        """Run inference on a single BGR frame (HWC uint8).

        Returns normalized bbox coords so the result is resolution-agnostic.
        """
        h, w = frame.shape[:2]
        results = self.model.predict(
            frame,
            conf=self.conf,
            iou=self.iou,
            device=self.device,
            verbose=False,
        )

        detections: list[RawDetection] = []
        for r in results:
            for box in r.boxes:
                raw_cls = r.names[int(box.cls)]
                canonical = _COCO_TO_CANONICAL.get(raw_cls, raw_cls)
                if canonical not in (
                    set(_COCO_TO_CANONICAL.values()) | _CUSTOM_CLASSES
                ):
                    continue

                x1, y1, x2, y2 = box.xyxy[0].tolist()
                detections.append(
                    RawDetection(
                        track_id=-1,  # assigned by tracker
                        class_name=canonical,
                        confidence=float(box.conf),
                        bbox=(x1 / w, y1 / h, x2 / w, y2 / h),
                    )
                )

        return detections
