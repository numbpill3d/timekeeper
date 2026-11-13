"""Live event WebSocket lifecycle tests."""

import asyncio
import os
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import ClassVar
from uuid import uuid4

os.environ.setdefault("JWT_SECRET", "unit-test-secret-012345678901234567890123")

import pytest
from omniscient_shared.models.event import Event, EventType

from api.src.ws import stream


def _event() -> Event:
    return Event(
        camera_id=uuid4(),
        event_type=EventType.person_entered,
        timestamp=datetime.now(UTC),
        action_label="Person entered",
    )


class _Acquire:
    def __init__(self, db):
        self.db = db

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, *_args):
        return None


class _Pool:
    def __init__(self, db):
        self.db = db

    def acquire(self):
        return _Acquire(self.db)


class _LabelDB:
    async def fetchrow(self, *_args):
        return {"person_label": "John", "object_label": "keys"}


class _BrokenLabelDB:
    async def fetchrow(self, *_args):
        raise RuntimeError("database unavailable")


def _socket_with_db(db):
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(db=_Pool(db)))
    )


@pytest.mark.asyncio
async def test_event_labels_are_resolved_from_the_authenticated_owner_db():
    person, item = await stream._event_labels(
        _socket_with_db(_LabelDB()), _event(), "owner-1"
    )
    assert (person, item) == ("John", "keys")


@pytest.mark.asyncio
async def test_event_label_lookup_fails_softly(caplog):
    person, item = await stream._event_labels(
        _socket_with_db(_BrokenLabelDB()), _event(), "owner-1"
    )
    assert (person, item) == (None, None)
    assert "live event labels unavailable" in caplog.text


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
    received_kwargs = {}

    def make_consumer(*args, **kwargs):
        received_kwargs.update(kwargs)
        return consumer

    monkeypatch.setattr(stream, "AIOKafkaConsumer", make_consumer)
    monkeypatch.setattr(stream, "decode_token", lambda token: {"sub": "owner-1"})

    await stream.events_stream(_WebSocket())

    assert consumer.cancelled is True
    assert consumer.stopped is True
    assert received_kwargs["group_id"].startswith("timekeeper-ws-")
