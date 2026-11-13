"""Best-effort camera ingestion health reporting."""

from __future__ import annotations

import logging

import asyncpg

log = logging.getLogger(__name__)


class CameraStatusReporter:
    """Persist throttled stream health without affecting frame delivery."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._pool: asyncpg.Pool | None = None

    async def start(self) -> None:
        if not self._database_url:
            return
        try:
            self._pool = await asyncpg.create_pool(
                self._database_url,
                min_size=1,
                max_size=2,
                timeout=15,
                command_timeout=5,
            )
        except Exception as exc:  # noqa: BLE001 - health is non-critical
            log.warning("camera health reporter unavailable (%s)", type(exc).__name__)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def report(
        self,
        camera_id: object,
        status: str,
        error_code: str | None = None,
        width: int | None = None,
        height: int | None = None,
        fps: float | None = None,
    ) -> None:
        pool = self._pool
        if pool is None:
            return
        try:
            async with pool.acquire() as conn:
                if status == "online":
                    await conn.execute(
                        """
                        UPDATE cameras
                        SET last_frame_at = NOW(),
                            last_error_at = NULL,
                            last_error_code = NULL,
                            consecutive_failures = 0,
                            last_frame_width = $2,
                            last_frame_height = $3,
                            observed_fps = $4
                        WHERE id = $1
                        """,
                        camera_id,
                        width,
                        height,
                        fps,
                    )
                else:
                    await conn.execute(
                        """
                        UPDATE cameras
                        SET last_error_at = NOW(),
                            last_error_code = $2,
                            consecutive_failures = LEAST(consecutive_failures + 1, 2147483647)
                        WHERE id = $1
                        """,
                        camera_id,
                        error_code or "stream_error",
                    )
        except (OSError, asyncpg.PostgresError, TimeoutError) as exc:
            # Health reporting must never terminate the stream worker. Keep the
            # log free of the camera URL and database error payload.
            log.warning("camera health update failed (%s)", type(exc).__name__)
