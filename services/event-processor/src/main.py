"""
Event processor: consumes detections, emits structured events.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

import asyncpg
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from omniscient_shared.kafka.topics import (
    DETECTIONS,
    EVENTS,
    GROUP_EVENT_PROCESSOR,
)
from omniscient_shared.models.entity import DetectionMessage

from .aggregator import CameraAggregator
from .correlator import Correlator
from .db import persist_event, purge_expired_events, store_clip
from .storage import cleanup_frame

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

_BROKERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
_DB_URL = os.getenv("DATABASE_URL", "")
_DB_CONNECT_TIMEOUT_SECONDS = 15
_RETENTION_INTERVAL = max(
    300, int(os.getenv("RETENTION_INTERVAL_SECONDS", "3600"))
)
_CAMERA_REFRESH_INTERVAL = max(
    1, int(os.getenv("CAMERA_REFRESH_INTERVAL_S", "30"))
)


class _DropDetection(Exception):
    """A valid message that is intentionally discarded and acknowledged."""


async def main() -> None:
    consumer = AIOKafkaConsumer(
        DETECTIONS,
        bootstrap_servers=_BROKERS,
        group_id=GROUP_EVENT_PROCESSOR,
        value_deserializer=lambda v: json.loads(v.decode()),
        enable_auto_commit=False,
    )
    producer = AIOKafkaProducer(
        bootstrap_servers=_BROKERS,
        value_serializer=lambda v: json.dumps(v).encode(),
    )

    aggregators: dict[str, CameraAggregator] = {}
    correlator = Correlator()
    consumer_started = False
    producer_started = False
    db: asyncpg.Connection | None = None
    retention_task: asyncio.Task | None = None
    camera_refresh_task: asyncio.Task | None = None
    try:
        await consumer.start()
        consumer_started = True
        await producer.start()
        producer_started = True
        db = await asyncpg.connect(_DB_URL, timeout=_DB_CONNECT_TIMEOUT_SECONDS)
        cam_rows = await db.fetch(
            "SELECT id, location_label, owner_id FROM cameras "
            "WHERE is_active = TRUE"
        )
        cam_locations = {str(r["id"]): r["location_label"] for r in cam_rows}
        cam_owners = {str(r["id"]): str(r["owner_id"]) for r in cam_rows}

        log.info("event processor started")
        # Retention uses its own connection. asyncpg connections do not allow
        # concurrent operations, and the consumer loop must remain free to
        # persist incoming detections while cleanup runs.
        retention_task = asyncio.create_task(_retention_loop())
        camera_refresh_task = asyncio.create_task(
            _camera_refresh_loop(cam_locations, cam_owners, aggregators, correlator)
        )
        async for msg in consumer:
            try:
                det_msg = DetectionMessage(**msg.value)
            except (TypeError, ValueError) as exc:
                log.warning(
                    "dropping malformed detection message (%s)", type(exc).__name__
                )
                await consumer.commit()
                continue
            cam_key = str(det_msg.camera_id)
            processed = False
            try:
                if cam_key not in cam_locations:
                    row = await db.fetchrow(
                        "SELECT location_label, owner_id FROM cameras "
                        "WHERE id = $1 AND is_active = TRUE",
                        det_msg.camera_id,
                    )
                    if not row:
                        log.warning("dropping detection for unknown/inactive camera %s", cam_key)
                        raise _DropDetection
                    cam_locations[cam_key] = row["location_label"]
                    cam_owners[cam_key] = str(row["owner_id"])

                if cam_key not in aggregators:
                    aggregators[cam_key] = CameraAggregator(
                        camera_id=cam_key,
                        location_label=cam_locations.get(cam_key),
                    )

                events = aggregators[cam_key].process(det_msg)
                owner_id = cam_owners.get(cam_key, "")

                # cross-camera correlation may produce additional events
                extra: list = []
                for evt in events:
                    evt.metadata["owner_id"] = owner_id
                    extra.extend(correlator.process(evt))
                events.extend(extra)

                for event in events:
                    event.metadata["owner_id"] = owner_id
                    if det_msg.frame_path and not event.clip_path:
                        event.clip_path = await store_clip(
                            det_msg.frame_path, event.id
                        )
                    await persist_event(db, event)
                    await producer.send(
                        EVENTS,
                        key=str(event.camera_id).encode(),
                        value=event.model_dump(mode="json"),
                    )
                processed = True
            except _DropDetection:
                processed = True
            except asyncio.CancelledError:
                raise
            except Exception:
                # Do not advance the group offset after a valid message fails.
                # Exiting lets the container restart and replay it instead of
                # auto-commit acknowledging the failed detection.
                log.exception(
                    "detection processing failed for camera %s; restarting for replay",
                    cam_key,
                )
            finally:
                if processed:
                    cleanup_frame(det_msg.frame_path)
            if not processed:
                raise RuntimeError("detection processing failed; replay required")
            await consumer.commit()
    finally:
        if retention_task:
            retention_task.cancel()
            await asyncio.gather(retention_task, return_exceptions=True)
        if camera_refresh_task:
            camera_refresh_task.cancel()
            await asyncio.gather(camera_refresh_task, return_exceptions=True)
        if consumer_started:
            await consumer.stop()
        if producer_started:
            await producer.stop()
        if db:
            await db.close()


async def _retention_loop() -> None:
    while True:
        retention_db: asyncpg.Connection | None = None
        try:
            retention_db = await asyncpg.connect(
                _DB_URL, timeout=_DB_CONNECT_TIMEOUT_SECONDS
            )
            deleted = await purge_expired_events(retention_db)
            if deleted:
                log.info("retention removed %d expired events", deleted)
        except asyncio.CancelledError:
            raise
        except (OSError, asyncpg.PostgresError, TimeoutError) as exc:
            log.warning("retention sweep unavailable (%s)", type(exc).__name__)
        finally:
            if retention_db:
                await retention_db.close()
        await asyncio.sleep(_RETENTION_INTERVAL)


async def _camera_refresh_loop(
    cam_locations: dict[str, str | None],
    cam_owners: dict[str, str],
    aggregators: dict[str, CameraAggregator],
    correlator: Correlator,
) -> None:
    """Refresh active-camera state without sharing the consumer DB connection."""
    while True:
        refresh_db: asyncpg.Connection | None = None
        try:
            refresh_db = await asyncpg.connect(
                _DB_URL, timeout=_DB_CONNECT_TIMEOUT_SECONDS
            )
            rows = await refresh_db.fetch(
                "SELECT id, location_label, owner_id FROM cameras "
                "WHERE is_active = TRUE"
            )
            active = {
                str(row["id"]): (row["location_label"], str(row["owner_id"]))
                for row in rows
            }
            for camera_id in set(cam_locations) - set(active):
                cam_locations.pop(camera_id, None)
                cam_owners.pop(camera_id, None)
                aggregators.pop(camera_id, None)
                correlator.remove_camera(camera_id)
            for camera_id, (location, owner_id) in active.items():
                cam_locations[camera_id] = location
                cam_owners[camera_id] = owner_id
                if camera_id in aggregators:
                    aggregators[camera_id].location_label = location
        except asyncio.CancelledError:
            raise
        except (OSError, asyncpg.PostgresError, TimeoutError) as exc:
            log.warning(
                "camera state refresh unavailable (%s)", type(exc).__name__
            )
        finally:
            if refresh_db:
                await refresh_db.close()
        await asyncio.sleep(_CAMERA_REFRESH_INTERVAL)
if __name__ == "__main__":
    asyncio.run(main())
