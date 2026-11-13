"""
Per-frame vision pipeline: detect -> track -> reid -> publish.

Perception stages (from §5.2):
  1. Detect objects/persons in frame (YOLOv8)
  2. Assign persistent track IDs (ByteTrack)
  3. Match persons across cameras (OSNet ReID)
  4. Publish DetectionMessage to Kafka 'detections' topic

Person identity:
  - At startup, the pipeline loads all known person embeddings from the
    database into an in-memory gallery.
  - On each detection, new persons (no gallery match) get a DB record
    created immediately with is_known=False.
  - Matched persons get their last_seen_at updated.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from uuid import UUID, uuid4

import aiofiles
import asyncpg
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

from .association import PersonCandidate, associate_person
from .detector import Detector
from .face import FaceModel
from .frame_storage import cleanup_unpublished_frame
from .gallery import (
    EMBEDDING_DIM,
    parse_gallery_embedding,
    remove_person_from_gallery,
    validate_embedding,
)
from .reid import ReIDModel
from .tracker import Tracker

log = logging.getLogger(__name__)

_DB_URL = os.getenv("DATABASE_URL", "")
_FRAME_ROOT = Path(os.getenv("FRAME_STORE_PATH", "/tmp/frames")).resolve()
_CAMERA_REFRESH_INTERVAL = max(
    1, int(os.getenv("CAMERA_REFRESH_INTERVAL_S", "30"))
)


class VisionPipeline:
    def __init__(self) -> None:
        device = os.getenv("TORCH_DEVICE", None)
        model = os.getenv("YOLO_MODEL", "yolov8n.pt")

        self.detector = Detector(model_path=model, device=device)
        self.reid = ReIDModel(device=device)
        self.face = FaceModel(device=device)

        # Per-camera tracker instances (ByteTrack is stateful per stream)
        self._trackers: dict[str, Tracker] = {}

        # ReID gallery scoped by owner_id: list of (person_id_str, embedding).
        # Never compare a camera against another account's identities.
        self._reid_gallery: dict[str, list[tuple[str, np.ndarray]]] = {}
        self._face_gallery: dict[str, list[tuple[str, np.ndarray]]] = {}

        # camera_id -> owner_id, populated from DB at startup
        self._cam_owners: dict[str, str] = {}

        # "{camera_id}:{track_id}:{class_name}" -> tracked_object UUID
        # Session-scoped; resets on restart (objects get new IDs per session)
        self._obj_map: dict[str, UUID] = {}

        self._db: asyncpg.Connection | None = None
        self._camera_refresh_task: asyncio.Task | None = None

        brokers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
        self._consumer = AIOKafkaConsumer(
            FRAMES,
            bootstrap_servers=brokers,
            group_id=GROUP_VISION,
            value_deserializer=lambda v: json.loads(v.decode()),
            enable_auto_commit=False,
        )
        self._producer = AIOKafkaProducer(
            bootstrap_servers=brokers,
            value_serializer=lambda v: json.dumps(v).encode(),
        )

    async def start(self) -> None:
        consumer_started = False
        producer_started = False
        try:
            if _DB_URL:
                self._db = await asyncpg.connect(_DB_URL)
                await self._load_gallery()
                self._camera_refresh_task = asyncio.create_task(
                    self._refresh_camera_state()
                )
            else:
                log.warning("DATABASE_URL not set; person identity disabled")

            await self._consumer.start()
            consumer_started = True
            await self._producer.start()
            producer_started = True
            log.info("vision pipeline started")

            async for msg in self._consumer:
                try:
                    await self._process(msg.value)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    # Preserve the offset so a restart replays a valid frame
                    # instead of allowing auto-commit to skip it permanently.
                    log.exception("frame processing failed; restarting for replay")
                    raise
                await self._consumer.commit()
        finally:
            if producer_started:
                await self._producer.stop()
            if consumer_started:
                await self._consumer.stop()
            if self._camera_refresh_task:
                self._camera_refresh_task.cancel()
                await asyncio.gather(
                    self._camera_refresh_task, return_exceptions=True
                )
            if self._db:
                await self._db.close()

    async def _load_gallery(self) -> None:
        """Populate in-memory ReID gallery and camera-owner map from DB."""
        assert self._db is not None
        cam_rows = await self._db.fetch(
            "SELECT id, owner_id FROM cameras WHERE is_active = TRUE"
        )
        self._cam_owners = {str(r["id"]): str(r["owner_id"]) for r in cam_rows}

        person_rows = await self._db.fetch(
            "SELECT id, owner_id, face_embedding, reid_embedding FROM persons "
            "WHERE face_embedding IS NOT NULL OR reid_embedding IS NOT NULL"
        )
        for row in person_rows:
            owner_id = str(row["owner_id"])
            person_id = str(row["id"])
            for column, gallery in (
                ("face_embedding", self._face_gallery),
                ("reid_embedding", self._reid_gallery),
            ):
                raw = row[column]
                if raw is None:
                    continue
                embedding = parse_gallery_embedding(raw, dimension=EMBEDDING_DIM)
                if embedding is None:
                    log.warning(
                        "skipping invalid %s embedding for person %s",
                        column,
                        person_id,
                    )
                    continue
                gallery.setdefault(owner_id, []).append(
                    (person_id, embedding)
                )

        log.info(
            "gallery loaded: %d persons, %d cameras",
            sum(len(gallery) for gallery in self._reid_gallery.values()),
            len(self._cam_owners),
        )

    async def _process(self, payload: dict) -> None:
        raw_frame_path = payload.get("frame_path") if isinstance(payload, dict) else None
        try:
            frame_msg = FrameMessage(**payload)
        except (TypeError, ValueError) as exc:
            cleanup_unpublished_frame(raw_frame_path if isinstance(raw_frame_path, str) else None)
            log.warning("bad frame message: %s", exc)
            return

        camera_key = str(frame_msg.camera_id)
        if camera_key not in self._cam_owners and self._db:
            row = await self._db.fetchrow(
                "SELECT owner_id FROM cameras WHERE id = $1 AND is_active = TRUE",
                frame_msg.camera_id,
            )
            if not row:
                cleanup_unpublished_frame(frame_msg.frame_path)
                log.warning("dropping frame for unknown/inactive camera %s", camera_key)
                return
            self._cam_owners[camera_key] = str(row["owner_id"])

        frame = await self._load_frame(frame_msg.frame_path)
        if frame is None:
            cleanup_unpublished_frame(frame_msg.frame_path)
            return
        tracker = self._trackers.setdefault(camera_key, Tracker())

        # Detector inference and tracker updates are synchronous and can be
        # expensive on CPU. Keep them off the event loop so Kafka heartbeats
        # and other service tasks remain responsive while one frame runs.
        tracked = await asyncio.to_thread(self._detect_and_track, frame, tracker)

        person_candidates: list[PersonCandidate] = []
        person_ids: dict[int, UUID | None] = {}
        for rd in tracked:
            if rd.class_name != "person":
                continue
            person_id = await self._reid_person(
                frame, rd.bbox, frame_msg.camera_id
            )
            person_ids[rd.track_id] = person_id
            if person_id:
                person_candidates.append(
                    PersonCandidate(person_id, rd.bbox, rd.confidence)
                )

        detections: list[Detection] = []
        for rd in tracked:
            # Only person detections may use the ReID identity map. Object
            # attribution must come from the geometric association below;
            # numeric tracker IDs can overlap between classes.
            person_id: UUID | None = (
                person_ids.get(rd.track_id) if rd.class_name == "person" else None
            )
            object_id: UUID | None = None
            association_confidence: float | None = None
            association_method: str | None = None
            if rd.class_name != "person":
                object_id = await self._get_or_create_object(
                    frame_msg.camera_id, rd.track_id, rd.class_name
                )
                association = associate_person(rd.bbox, person_candidates)
                if association:
                    person_id = association.person_id
                    association_confidence = association.confidence
                    association_method = association.method

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
                    object_id=object_id,
                    association_confidence=association_confidence,
                    association_method=association_method,
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
            key=str(frame_msg.camera_id).encode(),
            value=out.model_dump(mode="json"),
        )

        # The event processor still needs this shared frame to create an
        # evidence clip.  It owns cleanup after consuming the detection
        # message; deleting here races that consumer and silently loses clips.

    def _detect_and_track(
        self, frame: np.ndarray, tracker: Tracker
    ) -> list:
        raw = self.detector.detect(frame)
        return tracker.update(raw, frame.shape[:2])

    async def _load_frame(self, path: str) -> np.ndarray | None:
        try:
            p = Path(path).resolve()
            p.relative_to(_FRAME_ROOT)
        except (OSError, ValueError):
            log.warning("rejected frame path outside frame store: %s", path)
            return None
        if not p.exists():
            log.warning("frame not found: %s", path)
            return None
        async with aiofiles.open(p, "rb") as f:
            data = await f.read()
        arr = np.frombuffer(data, dtype=np.uint8)
        # JPEG decoding is synchronous native work. Keep it off the event
        # loop so a large frame cannot delay Kafka heartbeats or other camera
        # messages while the async file read itself remains non-blocking.
        frame = await asyncio.to_thread(cv2.imdecode, arr, cv2.IMREAD_COLOR)
        if frame is None:
            log.warning("could not decode frame: %s", path)
        return frame

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

        loop = asyncio.get_event_loop()
        face_emb, reid_emb = await asyncio.gather(
            loop.run_in_executor(None, self.face.extract, crop),
            loop.run_in_executor(None, self.reid.extract, crop),
            return_exceptions=True,
        )
        if isinstance(face_emb, Exception):
            log.warning("face extraction failed for camera %s: %s", camera_id, face_emb)
            face_emb = None
        if isinstance(reid_emb, Exception):
            log.warning("ReID extraction failed for camera %s: %s", camera_id, reid_emb)
            reid_emb = None
        face_emb = validate_embedding(face_emb)
        reid_emb = validate_embedding(reid_emb)
        if face_emb is None and reid_emb is None:
            return None

        owner_id_str = self._cam_owners.get(str(camera_id))
        if not owner_id_str:
            return None

        face_match = (
            self.face.match(face_emb, self._face_gallery.get(owner_id_str, []))
            if face_emb is not None
            else None
        )
        reid_match = (
            self.reid.match(reid_emb, self._reid_gallery.get(owner_id_str, []))
            if reid_emb is not None
            else None
        )
        match = face_match or reid_match
        if match:
            pid_str, _ = match
            person_id = UUID(pid_str)
            if self._db:
                updated = await self._db.execute(
                    "UPDATE persons SET last_seen_at = NOW() "
                    "WHERE id = $1 AND owner_id = $2",
                    person_id,
                    UUID(owner_id_str),
                )
                if updated == "UPDATE 0":
                    # A person can be deleted while this process still holds
                    # the startup gallery. Remove the stale identity and let
                    # this observation create a fresh unknown record instead
                    # of emitting an event with a dangling foreign key.
                    self._remove_from_galleries(pid_str)
                else:
                    return person_id
            else:
                return person_id

        # New person — create a DB record and add available embeddings.
        if self._db is None:
            return None

        face_literal = self._vector_literal(face_emb)
        reid_literal = self._vector_literal(reid_emb)
        short = uuid4().hex[:6].upper()
        row = await self._db.fetchrow(
            """
            INSERT INTO persons
                (owner_id, label, is_known, face_embedding, reid_embedding, last_seen_at)
            VALUES ($1, $2, FALSE, $3::vector, $4::vector, NOW())
            RETURNING id
            """,
            UUID(owner_id_str),
            f"Unknown {short}",
            face_literal,
            reid_literal,
        )
        if row is None:
            return None

        person_id = row["id"]
        if face_emb is not None:
            self._face_gallery.setdefault(owner_id_str, []).append(
                (str(person_id), face_emb)
            )
        if reid_emb is not None:
            self._reid_gallery.setdefault(owner_id_str, []).append(
                (str(person_id), reid_emb)
            )
        log.info("new person created: %s (camera %s)", person_id, camera_id)
        return person_id

    @staticmethod
    def _vector_literal(embedding: np.ndarray | None) -> str | None:
        embedding = validate_embedding(embedding)
        if embedding is None:
            return None
        return "[" + ",".join(f"{v:.6f}" for v in embedding) + "]"

    async def _get_or_create_object(
        self,
        camera_id: UUID,
        track_id: int,
        class_name: str,
    ) -> UUID | None:
        """Return stable UUID for this tracked object within the session."""
        key = f"{camera_id}:{track_id}:{class_name}"
        if self._db is None:
            return None
        if key in self._obj_map:
            obj_id = self._obj_map[key]
            owner_id_str = self._cam_owners.get(str(camera_id))
            if not owner_id_str:
                return None
            updated = await self._db.execute(
                "UPDATE tracked_objects SET last_camera_id = $1, "
                "last_seen_at = NOW() WHERE id = $2 AND owner_id = $3",
                camera_id,
                obj_id,
                UUID(owner_id_str),
            )
            if updated != "UPDATE 0":
                return obj_id
            # Camera ownership or the object row may have changed since this
            # session cached the mapping. Recreate it instead of returning a
            # foreign or dangling object ID.
            self._obj_map.pop(key, None)

        owner_id_str = self._cam_owners.get(str(camera_id))
        if not owner_id_str:
            return None

        row = await self._db.fetchrow(
            """
            INSERT INTO tracked_objects
                (owner_id, category, last_camera_id, last_seen_at)
            VALUES ($1, $2, $3, NOW())
            RETURNING id
            """,
            UUID(owner_id_str),
            class_name,
            camera_id,
        )
        if row is None:
            return None

        obj_id = row["id"]
        self._obj_map[key] = obj_id
        return obj_id

    def update_reid_gallery(
        self, gallery: list[tuple[str, np.ndarray]], owner_id: str
    ) -> None:
        """Replace one owner's gallery after a person enrollment update."""
        self._reid_gallery[owner_id] = gallery

    def _remove_from_galleries(self, person_id: str) -> None:
        for gallery in (self._face_gallery, self._reid_gallery):
            remove_person_from_gallery(gallery, person_id)

    async def _refresh_camera_state(self) -> None:
        """Refresh active camera ownership and evict stale tracker state."""
        while True:
            refresh_db: asyncpg.Connection | None = None
            try:
                refresh_db = await asyncpg.connect(_DB_URL)
                rows = await refresh_db.fetch(
                    "SELECT id, owner_id FROM cameras WHERE is_active = TRUE"
                )
                active = {
                    str(row["id"]): str(row["owner_id"]) for row in rows
                }
                for camera_id in set(self._cam_owners) - set(active):
                    self._cam_owners.pop(camera_id, None)
                    self._trackers.pop(camera_id, None)
                    self._obj_map = {
                        key: value
                        for key, value in self._obj_map.items()
                        if not key.startswith(f"{camera_id}:")
                    }
                self._cam_owners.update(active)
            except asyncio.CancelledError:
                raise
            except (OSError, asyncpg.PostgresError) as exc:
                log.warning("camera state refresh unavailable: %s", exc)
            finally:
                if refresh_db:
                    await refresh_db.close()
            await asyncio.sleep(_CAMERA_REFRESH_INTERVAL)
