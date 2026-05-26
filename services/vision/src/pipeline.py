"""
Per-frame vision pipeline: detect -> track -> reid -> publish.

Perception stages (from §5.2):
  1. Detect objects/persons in frame (YOLOv8)
  2. Assign persistent track IDs (ByteTrack)
  3. Match persons across cameras (OSNet ReID)
  4. Publish DetectionMessage to Kafka 'detections' topic
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from uuid import UUID

import aiofiles
import cv2
import numpy as np
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from omniscient_shared.kafka.topics import (
    DETECTIONS,
    FRAMES,
    GROUP_VISION,
)
from omniscient_shared.models.entity import (
    Detection,
    DetectionMessage,
    FrameMessage,
)

from .detector import Detector
from .reid import ReIDModel
from .tracker import Tracker

log = logging.getLogger(__name__)


class VisionPipeline:
    def __init__(self) -> None:
        device = os.getenv("TORCH_DEVICE", None)
        model = os.getenv("YOLO_MODEL", "yolov8n.pt")

        self.detector = Detector(model_path=model, device=device)
        self.tracker = Tracker()
        self.reid = ReIDModel(device=device)

        # Per-camera tracker instances (ByteTrack is stateful per stream)
        self._trackers: dict[str, Tracker] = {}

        # ReID gallery: camera_id -> list of (person_id_str, embedding)
        self._reid_gallery: list[tuple[str, np.ndarray]] = []

        brokers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
        self._consumer = AIOKafkaConsumer(
            FRAMES,
            bootstrap_servers=brokers,
            group_id=GROUP_VISION,
            value_deserializer=lambda v: json.loads(v.decode()),
        )
        self._producer = AIOKafkaProducer(
            bootstrap_servers=brokers,
            value_serializer=lambda v: json.dumps(v).encode(),
        )

    async def start(self) -> None:
        await self._consumer.start()
        await self._producer.start()
        log.info("vision pipeline started")
        try:
            async for msg in self._consumer:
                await self._process(msg.value)
        finally:
            await self._consumer.stop()
            await self._producer.stop()

    async def _process(self, payload: dict) -> None:
        try:
            frame_msg = FrameMessage(**payload)
        except Exception as exc:
            log.warning("bad frame message: %s", exc)
            return

        frame = await self._load_frame(frame_msg.frame_path)
        if frame is None:
            return

        camera_key = str(frame_msg.camera_id)
        tracker = self._trackers.setdefault(camera_key, Tracker())

        raw = self.detector.detect(frame)
        tracked = tracker.update(raw, frame.shape[:2])

        detections: list[Detection] = []
        for rd in tracked:
            person_id: UUID | None = None

            if rd.class_name == "person":
                person_id = await self._reid_person(
                    frame, rd.bbox, frame_msg.camera_id
                )

            detections.append(
                Detection(
                    camera_id=frame_msg.camera_id,
                    timestamp=frame_msg.timestamp,
                    frame_id=frame_msg.frame_id,
                    track_id=rd.track_id,
                    class_name=rd.class_name,
                    confidence=rd.confidence,
                    bbox=rd.bbox,
                    person_id=person_id,
                )
            )

        out = DetectionMessage(
            camera_id=frame_msg.camera_id,
            timestamp=frame_msg.timestamp,
            frame_id=frame_msg.frame_id,
            frame_path=frame_msg.frame_path,
            detections=detections,
        )
        await self._producer.send(
            DETECTIONS,
            value=out.model_dump(mode="json"),
        )

    async def _load_frame(self, path: str) -> np.ndarray | None:
        p = Path(path)
        if not p.exists():
            log.warning("frame not found: %s", path)
            return None
        async with aiofiles.open(p, "rb") as f:
            data = await f.read()
        arr = np.frombuffer(data, dtype=np.uint8)
        return cv2.imdecode(arr, cv2.IMREAD_COLOR)

    async def _reid_person(
        self,
        frame: np.ndarray,
        bbox: tuple[float, float, float, float],
        camera_id: UUID,
    ) -> UUID | None:
        h, w = frame.shape[:2]
        x1 = int(bbox[0] * w)
        y1 = int(bbox[1] * h)
        x2 = int(bbox[2] * w)
        y2 = int(bbox[3] * h)
        crop = frame[max(0, y1):y2, max(0, x1):x2]

        if crop.size == 0:
            return None

        emb = await asyncio.get_event_loop().run_in_executor(
            None, self.reid.extract, crop
        )
        if emb is None:
            return None

        match = self.reid.match(emb, self._reid_gallery)
        if match:
            pid_str, _ = match
            return UUID(pid_str)

        return None

    def update_reid_gallery(
        self, gallery: list[tuple[str, np.ndarray]]
    ) -> None:
        self._reid_gallery = gallery
