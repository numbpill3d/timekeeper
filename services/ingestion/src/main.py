"""
Ingestion service entrypoint.

Loads active RTSP cameras from the database and starts one stream reader
task per camera. Polls DB every CAMERA_RELOAD_INTERVAL_S seconds to pick
up cameras added or deactivated at runtime without requiring a restart.
"""

from __future__ import annotations

import asyncio
import logging
import os

import asyncpg
from omniscient_shared.models.camera import Camera, CameraProtocol

from .frame_publisher import FramePublisher
from .stream import stream_camera

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

_DB_URL = os.getenv("DATABASE_URL", "")
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
            provider_config=r["provider_config"] or {},
        )
        for r in rows
    ]


async def main() -> None:
    publisher = FramePublisher()
    await publisher.start()

    # camera_id -> running task
    tasks: dict[str, asyncio.Task] = {}

    try:
        reload_backoff = 1.0
        while True:
            try:
                conn = await asyncpg.connect(_DB_URL)
                try:
                    cameras = await _load_cameras(conn)
                finally:
                    await conn.close()
                reload_backoff = 1.0
            except (OSError, asyncpg.PostgresError) as exc:
                log.warning(
                    "camera reload failed: %s — retrying in %.0fs",
                    exc,
                    reload_backoff,
                )
                await asyncio.sleep(reload_backoff)
                reload_backoff = min(reload_backoff * 2, 60.0)
                continue

            active_ids = {str(cam.id) for cam in cameras}

            # Cancel tasks for cameras that disappeared or were deactivated
            for cid in list(tasks):
                if cid not in active_ids or tasks[cid].done():
                    task = tasks[cid]
                    if task.done() and not task.cancelled():
                        error = task.exception()
                        if error:
                            log.warning("stream task failed for camera %s: %s", cid, error)
                    if cid not in active_ids:
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass
                        log.info("stopped stream for removed camera %s", cid)
                    del tasks[cid]

            # Start tasks for new cameras
            for cam in cameras:
                cid = str(cam.id)
                if cid not in tasks:
                    log.info("starting stream: %s (%s)", cam.name, cid)
                    tasks[cid] = asyncio.create_task(
                        stream_camera(cam, publisher.publish)
                    )

            await asyncio.sleep(_RELOAD_INTERVAL)
    except asyncio.CancelledError:
        pass
    finally:
        for task in tasks.values():
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks.values(), return_exceptions=True)
        await publisher.stop()


if __name__ == "__main__":
    asyncio.run(main())
