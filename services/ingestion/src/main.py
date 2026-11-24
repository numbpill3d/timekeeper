"""
Ingestion service entrypoint.

Loads active RTSP cameras from the database and starts one stream reader
task per camera. Polls DB every CAMERA_RELOAD_INTERVAL_S seconds to pick
up cameras added or deactivated at runtime without requiring a restart.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

import asyncpg
from omniscient_shared.models.camera import Camera, CameraProtocol

from .frame_publisher import FramePublisher
from .status import CameraStatusReporter
from .stream import stream_camera

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

_DB_URL = os.getenv("DATABASE_URL", "")
_DB_CONNECT_TIMEOUT_SECONDS = 15
try:
    _RELOAD_INTERVAL = max(1, int(os.getenv("CAMERA_RELOAD_INTERVAL_S", "30")))
except ValueError as exc:
    raise RuntimeError("CAMERA_RELOAD_INTERVAL_S must be an integer") from exc


async def _load_cameras(conn: asyncpg.Connection) -> list[Camera]:
    rows = await conn.fetch(
        "SELECT * FROM cameras WHERE is_active = TRUE "
        "AND is_edge_only = FALSE "
        "AND protocol IN ('rtsp', 'http', 'https', 'hls', 'file', 'onvif', "
        "'ring', 'nest', 'arlo', 'wyze')"
    )
    return [
        Camera(
            id=r["id"],
            owner_id=r["owner_id"],
            name=r["name"],
            stream_url=r["stream_url"],
            protocol=CameraProtocol(r["protocol"]),
            location_label=r["location_label"],
            is_edge_only=r["is_edge_only"],
            provider_config=json.loads(r["provider_config"]) or {},
        )
        for r in rows
    ]


def _camera_stream_signature(camera: Camera) -> tuple[str, str, str]:
    """Return settings that require replacing a running stream task."""
    return (
        camera.stream_url,
        camera.protocol.value,
        json.dumps(camera.provider_config, sort_keys=True, separators=(",", ":")),
    )


async def main() -> None:
    publisher = FramePublisher()
    await publisher.start()
    status = CameraStatusReporter(_DB_URL)
    await status.start()

    # camera_id -> running task
    tasks: dict[str, asyncio.Task] = {}
    # Keep the task's source settings alongside it so camera edits take effect
    # without requiring an ingestion-service restart.
    stream_signatures: dict[str, tuple[str, str, str]] = {}

    try:
        reload_backoff = 1.0
        while True:
            try:
                conn = await asyncpg.connect(
                    _DB_URL, timeout=_DB_CONNECT_TIMEOUT_SECONDS
                )
                try:
                    cameras = await _load_cameras(conn)
                finally:
                    await conn.close()
                reload_backoff = 1.0
            except (OSError, asyncpg.PostgresError, TimeoutError) as exc:
                log.warning(
                    "camera reload failed (%s) — retrying in %.0fs",
                    type(exc).__name__,
                    reload_backoff,
                )
                await asyncio.sleep(reload_backoff)
                reload_backoff = min(reload_backoff * 2, 60.0)
                continue

            cameras_by_id = {str(cam.id): cam for cam in cameras}
            active_ids = set(cameras_by_id)

            # Cancel tasks for cameras that disappeared or were deactivated
            for cid in list(tasks):
                settings_changed = (
                    cid in cameras_by_id
                    and stream_signatures.get(cid)
                    != _camera_stream_signature(cameras_by_id[cid])
                )
                if cid not in active_ids or settings_changed or tasks[cid].done():
                    task = tasks[cid]
                    if task.done() and not task.cancelled():
                        error = task.exception()
                        if error:
                            log.warning(
                                "stream task failed for camera %s (%s)",
                                cid,
                                type(error).__name__,
                            )
                    if cid not in active_ids:
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass
                        log.info("stopped stream for removed camera %s", cid)
                    elif settings_changed and not task.done():
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass
                        log.info("restarting stream for updated camera %s", cid)
                    del tasks[cid]
                    stream_signatures.pop(cid, None)

            # Start tasks for new cameras
            for cam in cameras:
                cid = str(cam.id)
                if cid not in tasks:
                    log.info("starting stream: %s (%s)", cam.name, cid)
                    tasks[cid] = asyncio.create_task(
                        stream_camera(cam, publisher.publish, status.report)
                    )
                    stream_signatures[cid] = _camera_stream_signature(cam)

            await asyncio.sleep(_RELOAD_INTERVAL)
    except asyncio.CancelledError:
        pass
    finally:
        for task in tasks.values():
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks.values(), return_exceptions=True)
        await publisher.stop()
        await status.close()


if __name__ == "__main__":
    asyncio.run(main())
