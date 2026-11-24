"""Bounded before-frame evidence and paired JPEG rendering."""

from __future__ import annotations

from collections import OrderedDict
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw

_MAX_FRAME_BYTES = 2 * 1024 * 1024
_MAX_CACHE_BYTES = 64 * 1024 * 1024
_MAX_CACHE_FRAMES = 512
_PANEL_SIZE = (640, 360)


def read_frame(path: Path) -> bytes | None:
    try:
        with path.open("rb") as source:
            data = source.read(_MAX_FRAME_BYTES + 1)
    except OSError:
        return None
    return data if 0 < len(data) <= _MAX_FRAME_BYTES else None


class RecentFrames:
    """Keep recent frames in memory after their shared-volume files are consumed."""

    def __init__(self) -> None:
        self._frames: OrderedDict[tuple[str, str], bytes] = OrderedDict()
        self._size = 0

    def remember(self, camera_id: str, frame_id: str, data: bytes) -> None:
        key = (camera_id, frame_id)
        self._size -= len(self._frames.pop(key, b""))
        self._frames[key] = data
        self._size += len(data)
        while self._size > _MAX_CACHE_BYTES or len(self._frames) > _MAX_CACHE_FRAMES:
            _, removed = self._frames.popitem(last=False)
            self._size -= len(removed)

    def get(self, camera_id: str, frame_id: str) -> bytes | None:
        return self._frames.get((camera_id, frame_id))

    def remove_camera(self, camera_id: str) -> None:
        for key in tuple(self._frames):
            if key[0] == camera_id:
                self._size -= len(self._frames.pop(key))


def write_comparison(before: bytes, after: Path, destination: str) -> None:
    width, height = _PANEL_SIZE
    with Image.new("RGB", (width * 2, height + 24), "#111111") as image:
        draw = ImageDraw.Draw(image)
        for index, (source, label) in enumerate(
            ((BytesIO(before), "Last seen"), (after, "After disappearance"))
        ):
            with Image.open(source, formats=["JPEG"]) as photo:
                photo.draft("RGB", _PANEL_SIZE)
                photo.thumbnail(_PANEL_SIZE)
                left = index * width
                image.paste(photo, (left + (width - photo.width) // 2, (height - photo.height) // 2))
                draw.text((left + 8, height + 5), label, fill="white")
        image.save(destination, format="JPEG", quality=88)
