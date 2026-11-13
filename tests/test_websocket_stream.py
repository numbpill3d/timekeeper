"""Live event WebSocket lifecycle tests."""

import asyncio
import os
from typing import ClassVar

os.environ.setdefault("JWT_SECRET", "unit-test-secret-012345678901234567890123")

import pytest

from api.src.ws import stream


class _WebSocket:
    headers: ClassVar[dict[str, str]] = {
        "sec-websocket-protocol": "timekeeper-auth, token"
    }

    async def accept(self, *, subprotocol):
        assert subprotocol == "timekeeper-auth"

    async def close(self, *, code):
        raise AssertionError(f"unexpected close: {code}")

    async def receive(self):
        return {"type": "websocket.disconnect"}

    async def send_json(self, payload):
        raise AssertionError(f"unexpected event: {payload}")


class _IdleConsumer:
    cancelled = False
    stopped = False

    async def start(self):
        return None

    async def stop(self):
        self.stopped = True

    async def getone(self):
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            self.cancelled = True
            raise


@pytest.mark.asyncio
async def test_idle_disconnect_stops_kafka_consumer(monkeypatch):
    consumer = _IdleConsumer()
    monkeypatch.setattr(stream, "AIOKafkaConsumer", lambda *args, **kwargs: consumer)
    monkeypatch.setattr(stream, "decode_token", lambda token: {"sub": "owner-1"})

    await stream.events_stream(_WebSocket())

    assert consumer.cancelled is True
    assert consumer.stopped is True
