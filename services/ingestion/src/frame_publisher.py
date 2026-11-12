"""Kafka producer wrapper for FrameMessages."""

from __future__ import annotations

import json
import os

from aiokafka import AIOKafkaProducer
from omniscient_shared.kafka.topics import FRAMES
from omniscient_shared.models.entity import FrameMessage

_BROKERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")


class FramePublisher:
    def __init__(self) -> None:
        self._producer = AIOKafkaProducer(
            bootstrap_servers=_BROKERS,
            value_serializer=lambda v: json.dumps(v).encode(),
        )

    async def start(self) -> None:
        await self._producer.start()

    async def stop(self) -> None:
        await self._producer.stop()

    async def publish(self, msg: FrameMessage) -> None:
        await self._producer.send(
            FRAMES,
            key=str(msg.camera_id).encode(),
            value=msg.model_dump(mode="json"),
        )
