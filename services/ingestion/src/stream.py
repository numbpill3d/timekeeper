"""
RTSP stream reader using PyAV (FFmpeg bindings).

Reads frames at the configured interval and writes JPEG files to
the shared frame store, then publishes FrameMessage to Kafka.
Supports graceful reconnect on stream drop.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

import cv2
from omniscient_shared.models.camera import Camera
from omniscient_shared.models.entity import FrameMessage

from .config import (
    NORMAL_RECONNECT_DELAY_S,
    parse_frame_interval,
    safe_stream_error_context,
)
from .providers import ProviderError, frames_for

log = logging.getLogger(__name__)

FRAME_DIR = Path(os.getenv("FRAME_STORE_PATH", "/tmp/frames"))


FRAME_INTERVAL_S = parse_frame_interval(
    os.getenv("FRAME_INTERVAL_S", "0.1")
)  # 10 fps default
STATUS_REPORT_INTERVAL_S = 15.0


async def _report_status(
    status_cb,
    camera: Camera,
    status: str,
    error_code: str | None = None,
    width: int | None = None,
    height: int | None = None,
    fps: float | None = None,
) -> None:
    if status_cb is None:
        return
    try:
        await status_cb(camera.id, status, error_code, width, height, fps)
    except Exception:  # noqa: BLE001 - health reporting is non-critical
        log.warning("camera health callback failed for %s", camera.name)


async def stream_camera(
    camera: Camera,
    publish_cb,  # async callable(FrameMessage)
    status_cb=None,
) -> None:
    """Continuously read a camera stream and publish frames.

    Reconnects automatically on disconnect with exponential backoff.
    """
    FRAME_DIR.mkdir(parents=True, exist_ok=True)
    backoff = 1.0

    while True:
        try:
            await _read_loop(camera, publish_cb, status_cb)
            backoff = 1.0
            # A clean EOF is common for local-file feeds. Avoid a hot loop
            # that reopens and replays the source continuously at full CPU.
            await asyncio.sleep(NORMAL_RECONNECT_DELAY_S)
        except (ProviderError, OSError) as exc:
            await _report_status(status_cb, camera, "error", type(exc).__name__)
            log.warning(
                "stream error for %s — retrying in %.0fs",
                safe_stream_error_context(camera, exc), backoff,
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60.0)
        except Exception as exc:  # noqa: BLE001 - keep camera tasks alive
            # Kafka/client failures are recoverable stream errors too. Without
            # this boundary a single publish failure permanently kills the
            # camera task while the reload loop still considers it present.
            # Do not emit a traceback here: provider/client exceptions can
            # contain the configured stream URL or other connection details.
            await _report_status(status_cb, camera, "error", type(exc).__name__)
            log.error(
                "unexpected stream failure for %s — retrying in %.0fs",
                safe_stream_error_context(camera, exc),
                backoff,
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60.0)
        except asyncio.CancelledError:
            break


async def _read_loop(camera: Camera, publish_cb, status_cb=None) -> None:
    last_publish = 0.0
    last_status_report: float | None = None
    frames_since_status = 0
    async for img in frames_for(camera):
        # PTS is not comparable across reconnects; use wall-clock time to
        # enforce the sampling interval consistently for live and file feeds.
        now = asyncio.get_running_loop().time()
        if now - last_publish < FRAME_INTERVAL_S:
            continue
        last_publish = now

        frame_id = str(uuid.uuid4())
        path = FRAME_DIR / f"{frame_id}.jpg"
        published = False
        try:
            encoded = await asyncio.to_thread(
                cv2.imwrite,
                str(path),
                img,
                [cv2.IMWRITE_JPEG_QUALITY, 85],
            )
            if not encoded:
                log.warning("could not encode frame for %s", camera.name)
                continue

            msg = FrameMessage(
                camera_id=camera.id,
                timestamp=datetime.now(tz=UTC),
                frame_id=frame_id,
                frame_path=str(path),
                width=img.shape[1],
                height=img.shape[0],
            )
            await publish_cb(msg)
            published = True
            frames_since_status += 1
            if last_status_report is None:
                await _report_status(
                    status_cb,
                    camera,
                    "online",
                    width=msg.width,
                    height=msg.height,
                )
                last_status_report = now
                frames_since_status = 0
            elif now - last_status_report >= STATUS_REPORT_INTERVAL_S:
                elapsed = max(now - last_status_report, 1.0)
                await _report_status(
                    status_cb,
                    camera,
                    "online",
                    width=msg.width,
                    height=msg.height,
                    fps=min(frames_since_status / elapsed, 120.0),
                )
                last_status_report = now
                frames_since_status = 0
        finally:
            if not published:
                path.unlink(missing_ok=True)
