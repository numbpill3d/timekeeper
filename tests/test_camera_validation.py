"""Camera input validation must not persist credentials."""

import pytest
from omniscient_shared.models.entity import Detection, FrameMessage
from pydantic import ValidationError

from api.src.routes.cameras import CameraCreate


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
