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
from .db import persist_event, store_clip

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

_BROKERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
_DB_URL = os.getenv("DATABASE_URL", "")


async def main() -> None:
    consumer = AIOKafkaConsumer(
        DETECTIONS,
        bootstrap_servers=_BROKERS,
        group_id=GROUP_EVENT_PROCESSOR,
        value_deserializer=lambda v: json.loads(v.decode()),
    )
    producer = AIOKafkaProducer(
        bootstrap_servers=_BROKERS,
        value_serializer=lambda v: json.dumps(v).encode(),
    )

    await consumer.start()
    await producer.start()
    db = await asyncpg.connect(_DB_URL)

    aggregators: dict[str, CameraAggregator] = {}
    correlator = Correlator()

    cam_rows = await db.fetch(
        "SELECT id, location_label, owner_id FROM cameras"
    )
    cam_locations = {str(r["id"]): r["location_label"] for r in cam_rows}
    cam_owners = {str(r["id"]): str(r["owner_id"]) for r in cam_rows}

    log.info("event processor started")
    try:
        async for msg in consumer:
            det_msg = DetectionMessage(**msg.value)
            cam_key = str(det_msg.camera_id)

            if cam_key not in aggregators:
                aggregators[cam_key] = CameraAggregator(
                    camera_id=cam_key,
                    location_label=cam_locations.get(cam_key),
                )

            events = aggregators[cam_key].process(det_msg)

            # cross-camera correlation may produce additional events
            extra: list = []
            for evt in events:
                extra.extend(correlator.process(evt))
            events.extend(extra)

            owner_id = cam_owners.get(cam_key, "")
            for event in events:
                event.metadata["owner_id"] = owner_id
                if det_msg.frame_path and not event.clip_path:
                    event.clip_path = await store_clip(
                        det_msg.frame_path, event.id
                    )
                await persist_event(db, event)
                await producer.send(
                    EVENTS, value=event.model_dump(mode="json")
                )
    finally:
        await consumer.stop()
        await producer.stop()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
