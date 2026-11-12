"""Camera input validation must not persist credentials."""

import pytest
from pydantic import ValidationError

from api.src.routes.cameras import CameraCreate


def test_stream_url_rejects_embedded_credentials():
    with pytest.raises(ValidationError, match="embedded credentials"):
        CameraCreate(
            name="front door",
            stream_url="rtsp://camera:password@example.test/live",
        )


def test_provider_config_rejects_camel_case_token_key():
    with pytest.raises(ValidationError, match="provider_config"):
        CameraCreate(
            name="front door",
            stream_url="ring://camera-1",
            provider_config={"accessToken": "should-not-be-stored"},
        )
