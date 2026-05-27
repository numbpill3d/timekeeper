"""
WebSocket endpoint: /ws/events

Streams live activity events to connected clients as they arrive
from the Kafka 'events' topic. Each connected user only receives
events from their own cameras.

Connection: ws://host/ws/events?token=<jwt>
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

from aiokafka import AIOKafkaConsumer
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from ..auth import decode_token

log = logging.getLogger(__name__)

router = APIRouter()

_BROKERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")


@router.websocket("/ws/events")
async def events_stream(websocket: WebSocket) -> None:
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001)
        return

    try:
        user = decode_token(token)
    except Exception:
        await websocket.close(code=4001)
        return

    owner_id = user["sub"]
    await websocket.accept()
    log.info("ws client connected: %s", owner_id)

    consumer = AIOKafkaConsumer(
        "omniscient.events",
        bootstrap_servers=_BROKERS,
        value_deserializer=lambda v: json.loads(v.decode()),
        auto_offset_reset="latest",
    )
    await consumer.start()

    try:
        async for msg in consumer:
            event = msg.value
            # Filter to this user's cameras on the fly.
            # The event-processor already scoped events to real cameras;
            # ownership check here is the security gate.
            cam_owner = event.get("metadata", {}).get("owner_id")
            if cam_owner != owner_id:
                continue

            try:
                await websocket.send_json(event)
            except WebSocketDisconnect:
                break
    except WebSocketDisconnect:
        pass
    except asyncio.CancelledError:
        pass
    finally:
        await consumer.stop()
        log.info("ws client disconnected: %s", owner_id)
