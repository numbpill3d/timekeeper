"""
WebSocket endpoint: /ws/events

Streams live activity events to connected clients as they arrive
from the Kafka 'events' topic. Each connected user only receives
events from their own cameras.

Connection: WebSocket subprotocols ["timekeeper-auth", "<jwt>"].
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

from aiokafka import AIOKafkaConsumer
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from omniscient_shared.models.event import Event

from ..auth import decode_token
from .payload import public_event_payload

log = logging.getLogger(__name__)

router = APIRouter()

_BROKERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")


@router.websocket("/ws/events")
async def events_stream(websocket: WebSocket) -> None:
    protocols = [
        value.strip()
        for value in websocket.headers.get("sec-websocket-protocol", "").split(",")
    ]
    try:
        token = protocols[protocols.index("timekeeper-auth") + 1]
    except (ValueError, IndexError):
        token = ""
    if not token:
        await websocket.close(code=4001)
        return

    try:
        user = decode_token(token)
    except HTTPException:
        await websocket.close(code=4001)
        return

    owner_id = user["sub"]
    await websocket.accept(subprotocol="timekeeper-auth")
    log.info("ws client connected: %s", owner_id)

    consumer = AIOKafkaConsumer(
        "omniscient.events",
        bootstrap_servers=_BROKERS,
        value_deserializer=lambda v: json.loads(v.decode()),
        auto_offset_reset="latest",
    )
    consumer_started = False
    try:
        try:
            await consumer.start()
            consumer_started = True
        except Exception:
            log.exception("live event broker unavailable")
            await websocket.close(code=1011)
            return

        # Kafka's async iterator can wait indefinitely when the topic is idle.
        # Race each read with a receive so an idle disconnected browser releases
        # its consumer promptly instead of leaking a broker connection.
        disconnect_task: asyncio.Task[object] | None = asyncio.create_task(
            websocket.receive()
        )
        try:
            while True:
                consumer_task = asyncio.create_task(consumer.getone())
                done, _ = await asyncio.wait(
                    (consumer_task, disconnect_task),
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if disconnect_task in done:
                    consumer_task.cancel()
                    await asyncio.gather(consumer_task, return_exceptions=True)
                    try:
                        message = disconnect_task.result()
                    except WebSocketDisconnect:
                        break
                    if message.get("type") == "websocket.disconnect":
                        break
                    # Ignore client messages and continue watching for a close.
                    disconnect_task = asyncio.create_task(websocket.receive())
                    continue

                msg = consumer_task.result()
                try:
                    event = Event.model_validate(msg.value)
                except (TypeError, ValueError) as exc:
                    log.warning("dropping malformed live event: %s", exc)
                    continue
                # Filter to this user's cameras on the fly.
                # The event-processor already scoped events to real cameras;
                # ownership check here is the security gate.
                cam_owner = event.metadata.get("owner_id")
                if cam_owner != owner_id:
                    continue

                try:
                    payload = public_event_payload(event)
                    if payload is not None:
                        await websocket.send_json(payload)
                except WebSocketDisconnect:
                    break
        finally:
            if not disconnect_task.done():
                disconnect_task.cancel()
            await asyncio.gather(disconnect_task, return_exceptions=True)
    except WebSocketDisconnect:
        pass
    except asyncio.CancelledError:
        raise
    finally:
        if consumer_started:
            await consumer.stop()
        log.info("ws client disconnected: %s", owner_id)
