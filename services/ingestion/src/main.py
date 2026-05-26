"""
Ingestion service entrypoint.

Loads active cameras from the database and starts one stream reader
task per camera. Restarts individual tasks on failure without
affecting other streams.
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


async def load_cameras(conn: asyncpg.Connection) -> list[Camera]:
    rows = await conn.fetch(
        "SELECT * FROM cameras WHERE is_active = TRUE AND protocol = 'rtsp'"
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
        )
        for r in rows
    ]


async def main() -> None:
    publisher = FramePublisher()
    await publisher.start()

    conn = await asyncpg.connect(_DB_URL)
    cameras = await load_cameras(conn)
    await conn.close()

    log.info("starting streams for %d cameras", len(cameras))

    tasks = [
        asyncio.create_task(stream_camera(cam, publisher.publish))
        for cam in cameras
    ]
    try:
        await asyncio.gather(*tasks)
    finally:
        await publisher.stop()


if __name__ == "__main__":
    asyncio.run(main())
