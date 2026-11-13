"""Ingestion logging must not expose camera credentials or endpoints."""

from uuid import uuid4

from config import safe_stream_error_context
from omniscient_shared.models.camera import Camera, CameraProtocol


def test_stream_error_context_omits_url_and_exception_text():
    camera = Camera(
        owner_id=uuid4(),
        name="front door",
        stream_url="rtsp://user:password@example.test/live?token=secret",
        protocol=CameraProtocol.rtsp,
    )

    context = safe_stream_error_context(
        camera, RuntimeError("request failed for rtsp://user:password@example.test")
    )

    assert context == "front door (rtsp): RuntimeError"
    assert "password" not in context
    assert "example.test" not in context
