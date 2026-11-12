"""Camera input validation must not persist credentials."""

import pytest
from omniscient_shared.models.entity import Detection, DetectionMessage, FrameMessage
from omniscient_shared.models.event import Event, EventType
from pydantic import ValidationError

from api.src.routes.cameras import CameraCreate, _public_camera


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
