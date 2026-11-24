"""Smoke-test application startup imports that unit tests otherwise bypass."""

import os
from uuid import uuid4

os.environ.setdefault("JWT_SECRET", "test-secret-for-unit-tests-only-must-be-32c")

from omniscient_shared.models.camera import Camera, CameraProtocol

from api.src.main import app
from services.ingestion.src.main import _camera_stream_signature, _load_cameras
from services.ingestion.src.status import CameraStatusReporter


def test_api_entrypoint_imports_with_runtime_dependencies():
    paths = {
        path
        for route in app.routes
        if (path := getattr(route, "path", None)) is not None
    }
    assert "/health" in paths


def test_ingestion_stream_signature_changes_when_source_settings_change():
    camera = Camera(
        owner_id=uuid4(),
        name="front door",
        stream_url="rtsp://camera/one",
        protocol=CameraProtocol.rtsp,
        provider_config={"access_token_env": "RING_ACCESS_TOKEN"},
    )
    original = _camera_stream_signature(camera)

    assert original != _camera_stream_signature(
        camera.model_copy(update={"stream_url": "rtsp://camera/two"})
    )
    assert original != _camera_stream_signature(
        camera.model_copy(update={"protocol": CameraProtocol.http})
    )
    assert original != _camera_stream_signature(
        camera.model_copy(update={"provider_config": {"whep_url": "https://camera/live"}})
    )


def test_camera_status_reporter_is_disabled_without_database_url():
    reporter = CameraStatusReporter("")
    assert reporter._pool is None


def test_ingestion_loads_multiple_active_cameras_independently():
    class CameraDb:
        async def fetch(self, _sql: str):
            return [
                {
                    "id": uuid4(),
                    "owner_id": uuid4(),
                    "name": "front door",
                    "stream_url": "rtsp://front-door/live",
                    "protocol": "rtsp",
                    "location_label": "front door",
                    "is_edge_only": False,
                    "provider_config": "{}",
                },
                {
                    "id": uuid4(),
                    "owner_id": uuid4(),
                    "name": "garage",
                    "stream_url": "http://garage/live",
                    "protocol": "http",
                    "location_label": "garage",
                    "is_edge_only": False,
                    "provider_config": '{"stream_url": "http://garage/live"}',
                },
            ]

    import asyncio

    cameras = asyncio.run(_load_cameras(CameraDb()))

    assert [camera.name for camera in cameras] == ["front door", "garage"]
    assert len({camera.id for camera in cameras}) == 2
    assert {camera.protocol for camera in cameras} == {
        CameraProtocol.rtsp,
        CameraProtocol.http,
    }
