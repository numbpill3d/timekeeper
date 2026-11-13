"""Camera input validation must not persist credentials."""

import pytest
from fastapi import HTTPException
from omniscient_shared.models.entity import Detection, DetectionMessage, FrameMessage
from omniscient_shared.models.event import Event, EventType
from pydantic import ValidationError

from api.src.routes.cameras import (
    CameraCreate,
    CameraUpdate,
    _public_camera,
    delete_camera,
    update_camera,
)


def test_stream_url_rejects_embedded_credentials():
    with pytest.raises(ValidationError, match="embedded credentials"):
        CameraCreate(
            name="front door",
            stream_url="rtsp://camera:password@example.test/live",
        )


@pytest.mark.parametrize(
    "stream_url",
    [
        "rtsp://camera.example/live?access_token=secret",
        "https://camera.example/live?client_secret=secret",
        "https://camera.example/live?refresh_token=secret",
        "https://camera.example/live#secret",
    ],
)
def test_stream_url_rejects_credential_like_query_or_fragment(stream_url):
    with pytest.raises(ValidationError, match="credential"):
        CameraCreate(name="front door", stream_url=stream_url)


def test_provider_config_rejects_camel_case_token_key():
    with pytest.raises(ValidationError, match="provider_config"):
        CameraCreate(
            name="front door",
            stream_url="ring://camera-1",
            provider_config={"accessToken": "should-not-be-stored"},
        )


def test_provider_config_rejects_credentials_in_nested_endpoint():
    with pytest.raises(ValidationError, match="provider endpoint"):
        CameraCreate(
            name="front door",
            stream_url="arlo://camera-1",
            provider_config={"rtsp_url": "rtsp://user:password@camera/live"},
        )


def test_provider_config_is_bounded():
    with pytest.raises(ValidationError, match="16 KiB"):
        CameraCreate(
            name="front door",
            stream_url="rtsp://camera/live",
            provider_config={"notes": "x" * 16385},
        )


def test_legacy_camera_output_redacts_credentials():
    camera = _public_camera(
        {
            "id": "00000000-0000-0000-0000-000000000001",
            "name": "legacy",
            "stream_url": "rtsp://user:password@camera/live?token=secret&quality=high#fragment",
            "protocol": "rtsp",
            "location_label": None,
            "is_edge_only": False,
            "is_active": True,
            "provider_config": {
                "access_token": "secret",
                "whep_url": "https://camera.example/live?token=secret",
                "refresh_token": "secret",
            },
        }
    )
    assert camera.stream_url == "rtsp://camera/live?quality=high"
    assert camera.provider_config == {"whep_url": "https://camera.example/live"}


def test_camera_metadata_is_bounded():
    with pytest.raises(ValidationError):
        CameraCreate(name="x" * 121, stream_url="rtsp://camera/stream")
    with pytest.raises(ValidationError):
        CameraCreate(name="front", stream_url="rtsp://camera/" + "x" * 2040)
    with pytest.raises(ValidationError):
        CameraCreate(
            name="front",
            stream_url="rtsp://camera/stream",
            location_label="x" * 121,
        )


def test_camera_updates_reject_blank_names_and_normalize_locations():
    with pytest.raises(ValidationError, match="name cannot be empty"):
        CameraUpdate(name="   ")
    assert CameraUpdate(name="  garage  ", location_label="  back door ").model_dump(
        exclude_none=True
    ) == {"name": "garage", "location_label": "back door"}


def test_camera_update_preserves_explicit_null_location_for_patch():
    update = CameraUpdate(location_label=None)
    assert update.model_dump(exclude_unset=True) == {"location_label": None}


def test_camera_update_can_change_source_without_storing_credentials():
    update = CameraUpdate(
        stream_url="  https://camera.example/live  ",
        protocol="https",
    )
    assert update.model_dump(exclude_unset=True) == {
        "stream_url": "https://camera.example/live",
        "protocol": "https",
    }
    with pytest.raises(ValidationError, match="credential"):
        CameraUpdate(stream_url="https://camera.example/live?token=secret")


def test_edge_only_camera_requires_an_external_agent():
    with pytest.raises(ValidationError, match="external edge agent"):
        CameraCreate(
            name="front",
            stream_url="rtsp://camera/stream",
            is_edge_only=True,
        )


def test_detection_contract_rejects_invalid_bounds():
    with pytest.raises(ValidationError):
        Detection(
            camera_id="00000000-0000-0000-0000-000000000001",
            timestamp="2026-01-01T00:00:00Z",
            frame_id="frame",
            track_id=1,
            class_name="keys",
            confidence=1.1,
            bbox=(0.1, 0.1, 0.5, 0.5),
        )
    with pytest.raises(ValidationError):
        FrameMessage(
            camera_id="00000000-0000-0000-0000-000000000001",
            timestamp="2026-01-01T00:00:00Z",
            frame_id="frame",
            frame_path="/tmp/frame.jpg",
            width=0,
            height=100,
        )


def test_detection_message_bounds_untrusted_frame_payloads():
    with pytest.raises(ValidationError):
        DetectionMessage(
            camera_id="00000000-0000-0000-0000-000000000001",
            timestamp="2026-01-01T00:00:00Z",
            frame_id="x" * 201,
        )
    with pytest.raises(ValidationError):
        DetectionMessage(
            camera_id="00000000-0000-0000-0000-000000000001",
            timestamp="2026-01-01T00:00:00Z",
            frame_id="frame",
            frame_path="x" * 1025,
        )


def test_detection_message_rejects_inner_camera_or_frame_mismatch():
    detection = {
        "camera_id": "00000000-0000-0000-0000-000000000002",
        "timestamp": "2026-01-01T00:00:00Z",
        "frame_id": "other-frame",
        "track_id": 1,
        "class_name": "person",
        "confidence": 0.9,
        "bbox": (0.1, 0.1, 0.5, 0.5),
    }
    with pytest.raises(ValidationError, match="camera_id"):
        DetectionMessage(
            camera_id="00000000-0000-0000-0000-000000000001",
            timestamp="2026-01-01T00:00:00Z",
            frame_id="frame",
            detections=[detection],
        )

    detection["camera_id"] = "00000000-0000-0000-0000-000000000001"
    with pytest.raises(ValidationError, match="frame_id"):
        DetectionMessage(
            camera_id="00000000-0000-0000-0000-000000000001",
            timestamp="2026-01-01T00:00:00Z",
            frame_id="frame",
            detections=[detection],
        )


def test_event_contract_rejects_oversized_or_non_json_metadata():
    base = {
        "camera_id": "00000000-0000-0000-0000-000000000001",
        "event_type": EventType.person_detected,
        "timestamp": "2026-01-01T00:00:00Z",
        "action_label": "person detected",
    }
    with pytest.raises(ValidationError):
        Event(**base, metadata={"payload": "x" * 16385})
    with pytest.raises(ValidationError):
        Event(**base, metadata={"payload": object()})


class _CameraDeleteTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


class _CameraUpdateDb:
    def __init__(self, row: dict | None) -> None:
        self.row = row
        self.query: tuple[str, tuple[object, ...]] | None = None

    async def fetchrow(self, sql: str, *params: object) -> dict | None:
        self.query = (sql, params)
        return self.row


@pytest.mark.asyncio
async def test_camera_update_returns_owner_scoped_row_atomically():
    db = _CameraUpdateDb(
        {
            "id": "00000000-0000-0000-0000-000000000001",
            "name": "garage",
            "stream_url": "rtsp://camera/live",
            "protocol": "rtsp",
            "location_label": "back door",
            "is_edge_only": False,
            "is_active": True,
            "provider_config": {},
        }
    )

    result = await update_camera(
        "00000000-0000-0000-0000-000000000001",
        CameraUpdate(name="garage"),
        {"sub": "owner-1"},
        db,
    )

    assert result.name == "garage"
    assert db.query is not None
    sql, params = db.query
    assert "WHERE id = $1 AND owner_id = $2" in sql
    assert "RETURNING *" in sql
    assert params == (
        "00000000-0000-0000-0000-000000000001",
        "owner-1",
        "garage",
    )


@pytest.mark.asyncio
async def test_camera_update_can_clear_location_label():
    db = _CameraUpdateDb(
        {
            "id": "00000000-0000-0000-0000-000000000001",
            "name": "garage",
            "stream_url": "rtsp://camera/live",
            "protocol": "rtsp",
            "location_label": None,
            "is_edge_only": False,
            "is_active": True,
            "provider_config": {},
        }
    )

    await update_camera(
        "00000000-0000-0000-0000-000000000001",
        CameraUpdate(location_label=None),
        {"sub": "owner-1"},
        db,
    )

    assert db.query is not None
    _sql, params = db.query
    assert params == (
        "00000000-0000-0000-0000-000000000001",
        "owner-1",
        None,
    )


@pytest.mark.asyncio
async def test_camera_update_maps_missing_owner_scoped_row_to_not_found():
    with pytest.raises(HTTPException) as exc_info:
        await update_camera(
            "00000000-0000-0000-0000-000000000001",
            CameraUpdate(name="garage"),
            {"sub": "owner-1"},
            _CameraUpdateDb(None),
        )
    assert exc_info.value.status_code == 404


class _CameraDeleteDb:
    def __init__(self) -> None:
        self.queries: list[tuple[str, tuple[object, ...]]] = []

    def transaction(self) -> _CameraDeleteTransaction:
        return _CameraDeleteTransaction()

    async def fetchval(self, sql: str, *params: object) -> int:
        self.queries.append((sql, params))
        return 1

    async def fetch(self, sql: str, *params: object) -> list[dict]:
        self.queries.append((sql, params))
        return [{"id": "event-1", "clip_path": "clips/event-1.jpg"}]

    async def execute(self, sql: str, *params: object) -> str:
        self.queries.append((sql, params))
        return "DELETE 1"


@pytest.mark.asyncio
async def test_camera_delete_removes_history_and_clips_after_commit(monkeypatch):
    db = _CameraDeleteDb()
    deleted: list[list[str | None]] = []

    async def fake_delete(values: list[str | None]) -> None:
        deleted.append(values)

    monkeypatch.setattr("api.src.routes.cameras.delete_clip_objects", fake_delete)

    await delete_camera("camera-1", {"sub": "owner-1"}, db)

    statements = [query for query, _ in db.queries]
    assert "DELETE FROM detections WHERE camera_id = $1" in statements
    assert "DELETE FROM events WHERE camera_id = $1" in statements
    assert "DELETE FROM cameras WHERE id = $1" in statements
    assert deleted == [["clips/event-1.jpg"]]
