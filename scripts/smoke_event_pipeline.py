"""Exercise Kafka -> event processor -> TimescaleDB -> authenticated API and media.

Run against an isolated, disposable Compose project with event-processor and
api running. This creates an account and synthetic observations in that stack.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import monotonic, sleep
from urllib.error import URLError
from urllib.request import Request, urlopen
from uuid import UUID, uuid4

_COMPOSE = ["docker", "compose", "--env-file", ".env.example"]
_API = "http://127.0.0.1:8000"


def api(path: str, token: str = "", payload: dict | None = None, method: str | None = None):
    body = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with urlopen(Request(f"{_API}{path}", body, headers, method=method), timeout=5) as response:
        return json.load(response)


def wait_for(check, description: str, timeout: int = 60):
    deadline = monotonic() + timeout
    last_error = None
    while monotonic() < deadline:
        try:
            result = check()
            if result:
                return result
        except URLError as exc:
            last_error = exc
        sleep(0.5)
    raise RuntimeError(f"timed out waiting for {description}") from last_error


def run_in_worker(stage: str, owner_id: str, camera_id: str) -> None:
    subprocess.run(
        [*_COMPOSE, "exec", "-T", "event-processor", "python", "-", stage, owner_id, camera_id],
        input=Path(__file__).read_text(),
        text=True,
        check=True,
        timeout=60,
    )


async def publish(stage: str, owner_id: UUID, camera_id: UUID) -> None:
    import asyncpg
    from aiokafka import AIOKafkaProducer
    from omniscient_shared.kafka.topics import DETECTIONS
    from omniscient_shared.models.entity import Detection, DetectionMessage
    from PIL import Image

    connection = await asyncpg.connect(os.environ["DATABASE_URL"], timeout=10)
    try:
        object_id = await connection.fetchval(
            "INSERT INTO tracked_objects (owner_id, category, last_camera_id) "
            "VALUES ($1, 'keys', $2) RETURNING id",
            owner_id,
            camera_id,
        )
        person_id = None
        if stage == "pickup":
            person_id = await connection.fetchval(
                "INSERT INTO persons (owner_id, label, is_known) "
                "VALUES ($1, 'Smoke Tester', TRUE) RETURNING id",
                owner_id,
            )
    finally:
        await connection.close()

    frame_store = Path(os.environ["FRAME_STORE_PATH"])
    frame_store.mkdir(exist_ok=True, parents=True)
    producer = AIOKafkaProducer(
        bootstrap_servers=os.environ["KAFKA_BOOTSTRAP_SERVERS"],
        request_timeout_ms=10000,
    )
    await producer.start()
    try:
        # Keep the source and destination on distinct Kafka partitions. Only
        # the restored correlator can join their events after the restart.
        partition = 0 if stage == "pickup" else 1
        now = datetime.now(UTC)
        offsets = [-10, -7, -1] if stage == "pickup" else [-3, 0]
        for index, offset in enumerate(offsets):
            frame_id = str(uuid4())
            timestamp = now + timedelta(seconds=offset)
            frame_path = frame_store / f"{frame_id}.jpg"
            with Image.new("RGB", (320, 180), "red" if index == 2 else "blue") as frame:
                frame.save(frame_path)
            detections = [] if index == 2 else [
                Detection(
                    camera_id=camera_id,
                    timestamp=timestamp,
                    frame_id=frame_id,
                    track_id=1,
                    class_name="keys",
                    confidence=0.96,
                    bbox=(0.3, 0.3, 0.5, 0.5),
                    person_id=person_id,
                    object_id=object_id,
                    association_confidence=0.85 if person_id else None,
                )
            ]
            message = DetectionMessage(
                camera_id=camera_id,
                timestamp=timestamp,
                frame_id=frame_id,
                frame_path=str(frame_path),
                detections=detections,
            )
            await producer.send_and_wait(
                DETECTIONS, message.model_dump_json().encode(),
                key=str(camera_id).encode(), partition=partition,
            )
        # A consumed file is removed only after the offset is committed.
        for _ in range(80):
            if not frame_path.exists():
                return
            await asyncio.sleep(0.5)
        raise RuntimeError(f"worker did not consume the {stage} sequence")
    finally:
        await producer.stop()


def smoke() -> None:
    wait_for(lambda: api("/health").get("status") == "ok", "API health")
    token = api("/auth/register", payload={
        "email": f"smoke-{uuid4().hex}@example.com",
        "password": uuid4().hex,
    })["access_token"]
    owner = api("/auth/me", token)["user_id"]

    def camera(name: str) -> str:
        return api("/cameras", token, {
            "name": name,
            "location_label": name,
            "stream_url": f"rtsp://{name}.example.com/live",
        })["id"]

    kitchen, garage = camera("kitchen"), camera("garage")
    updated = api(f"/cameras/{kitchen}", token, {
        "provider_config": {"rtsp_url": "rtsp://kitchen.example.com/backup"},
    }, method="PATCH")
    assert updated["provider_config"]["rtsp_url"].endswith("/backup"), updated

    def event(event_type: str, camera_id: str):
        rows = api(f"/events?event_type={event_type}&camera_id={camera_id}", token)
        return rows[0] if rows else None

    run_in_worker("pickup", owner, kitchen)
    pickup = wait_for(lambda: event("object_picked_up", kitchen), "pickup via API")
    assert pickup["action_label"] == "Possible pickup of keys", pickup
    assert pickup["person_label"] == "Smoke Tester", pickup
    detail = api(f"/events/{pickup['id']}", token)
    assert detail["clip_path"], detail
    with urlopen(detail["clip_path"], timeout=10) as response:
        assert response.read(2) == b"\xff\xd8", "signed evidence must be a JPEG"

    subprocess.run(
        [*_COMPOSE, "restart", "--timeout", "2", "event-processor"], check=True, timeout=30
    )
    run_in_worker("placement", owner, garage)
    handoff = wait_for(lambda: event("object_moved", garage), "restored cross-camera handoff")
    assert handoff["action_label"] == "Possible handoff of keys from kitchen to garage", handoff
    assert handoff["person_label"] == "Smoke Tester", handoff
    assert event("object_picked_up", kitchen)["id"] == pickup["id"]
    print("Verified signed evidence and cross-partition pickup recovery after restart.", flush=True)


if __name__ == "__main__":
    if len(sys.argv) == 4:
        asyncio.run(publish(sys.argv[1], UUID(sys.argv[2]), UUID(sys.argv[3])))
    else:
        smoke()
