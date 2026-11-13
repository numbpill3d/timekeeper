"""Provider adapter configuration tests (no live vendor credentials needed)."""

import asyncio
import sys
import types
from uuid import uuid4

import numpy as np
import pytest
from config import parse_frame_interval
from omniscient_shared.models.camera import Camera, CameraProtocol
from providers import (
    ProviderError,
    _configured_direct_camera,
    _device_id,
    _direct_frames,
    _OAuthCredentials,
    _provider_endpoint,
    _token,
)


def _camera(protocol: CameraProtocol, url: str, config: dict | None = None) -> Camera:
    return Camera(
        owner_id=uuid4(),
        name="test camera",
        stream_url=url,
        protocol=protocol,
        provider_config=config or {},
    )


def test_vendor_device_ids_strip_provider_scheme():
    assert _device_id(_camera(CameraProtocol.ring, "ring:abc")) == "ring:abc"
    assert _device_id(_camera(CameraProtocol.nest, "nest://device-1")) == "device-1"


def test_explicit_whep_endpoint_is_used(monkeypatch):
    monkeypatch.setenv("PROVIDER_ALLOWED_CONTROL_HOSTS", "example.test")
    camera = _camera(
        CameraProtocol.wyze,
        "wyze://cam-1",
        {"whep_url": "https://example.test/whep"},
    )
    assert _provider_endpoint(camera) == ("wyze", "https://example.test/whep")


def test_whep_endpoint_rejects_unapproved_host(monkeypatch):
    monkeypatch.delenv("PROVIDER_ALLOWED_CONTROL_HOSTS", raising=False)
    camera = _camera(
        CameraProtocol.wyze,
        "wyze://cam-1",
        {"whep_url": "https://attacker.example/whep"},
    )
    with pytest.raises(ProviderError, match="not in PROVIDER_ALLOWED_CONTROL_HOSTS"):
        _provider_endpoint(camera)


def test_whep_endpoint_rejects_embedded_credentials():
    camera = _camera(
        CameraProtocol.wyze,
        "wyze://cam-1",
        {"whep_url": "https://user:pass@example.test/whep"},
    )
    with pytest.raises(ProviderError, match="embedded credentials"):
        _provider_endpoint(camera)


def test_whep_endpoint_rejects_credential_query_parameter():
    camera = _camera(
        CameraProtocol.wyze,
        "wyze://cam-1",
        {"whep_url": "https://example.test/whep?token=secret"},
    )
    with pytest.raises(ProviderError, match="credential-like"):
        _provider_endpoint(camera)


@pytest.mark.parametrize("key", ["client_secret", "refresh_token"])
def test_provider_endpoint_rejects_all_credential_query_parameters(key):
    camera = _camera(
        CameraProtocol.wyze,
        "wyze://cam-1",
        {"whep_url": f"https://example.test/whep?{key}=secret"},
    )
    with pytest.raises(ProviderError, match="credential-like"):
        _provider_endpoint(camera)


def test_arlo_can_use_a_local_rtsp_bridge():
    camera = _camera(
        CameraProtocol.arlo,
        "arlo://cam-1",
        {"rtsp_url": "rtsp://127.0.0.1:8554/arlo-cam-1"},
    )
    direct = _configured_direct_camera(camera)
    assert direct is not None
    assert direct.protocol == CameraProtocol.rtsp
    assert direct.stream_url == "rtsp://127.0.0.1:8554/arlo-cam-1"


def test_cloud_provider_requires_endpoint_configuration(monkeypatch):
    monkeypatch.delenv("ARLO_WHEP_URL_TEMPLATE", raising=False)
    camera = _camera(CameraProtocol.arlo, "arlo://cam-1")
    with pytest.raises(ProviderError, match="provider_config.whep_url"):
        _provider_endpoint(camera)


def test_token_can_be_loaded_from_secret_file(monkeypatch, tmp_path):
    secret = tmp_path / "ring-token"
    secret.write_text("file-token\n", encoding="utf-8")
    monkeypatch.delenv("RING_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("RING_ACCESS_TOKEN_FILE", str(secret))
    assert _token({}, "RING_ACCESS_TOKEN") == "file-token"


@pytest.mark.asyncio
async def test_oauth_credentials_fail_closed_without_refresh_material(monkeypatch):
    monkeypatch.delenv("RING_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("RING_REFRESH_TOKEN", raising=False)
    with pytest.raises(ProviderError, match="RING_ACCESS_TOKEN"):
        await _OAuthCredentials({}, "ring").get()


def test_provider_config_cannot_select_unrelated_secret_env(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "do-not-send-this")
    with pytest.raises(ProviderError, match="uppercase RING_"):
        _OAuthCredentials({"access_token_env": "JWT_SECRET"}, "ring")


def test_frame_interval_is_bounded():
    assert parse_frame_interval("0.1") == 0.1
    with pytest.raises(RuntimeError, match="between"):
        parse_frame_interval("0")
    with pytest.raises(RuntimeError, match="between"):
        parse_frame_interval("61")
    with pytest.raises(RuntimeError, match="number"):
        parse_frame_interval("not-a-number")


def test_webrtc_adapter_completes_offer_answer_and_yields_video(monkeypatch):
    """Exercise the adapter handshake without requiring a camera or aiortc install."""
    captured: dict[str, str] = {}

    class FakeFrame:
        def to_ndarray(self, format: str):
            assert format == "bgr24"
            return np.zeros((2, 2, 3), dtype=np.uint8)

    class FakeTrack:
        kind = "video"

        async def recv(self):
            return FakeFrame()

    class FakePeerConnection:
        def __init__(self):
            self._track_handler = None
            self.localDescription = types.SimpleNamespace(sdp="fake-offer")

        def on(self, event):
            assert event == "track"
            def decorator(handler):
                self._track_handler = handler
                return handler
            return decorator

        def addTransceiver(self, kind, direction):
            assert direction == "recvonly"
            return object()

        def createDataChannel(self, label):
            assert label == "timekeeper"

        async def createOffer(self):
            return types.SimpleNamespace(sdp="fake-offer")

        async def setLocalDescription(self, offer):
            self.localDescription = offer

        async def setRemoteDescription(self, answer):
            self._track_handler(FakeTrack())

        async def close(self):
            return None

    fake_aiortc = types.SimpleNamespace(
        RTCPeerConnection=FakePeerConnection,
        RTCSessionDescription=lambda sdp, type: (sdp, type),
    )
    monkeypatch.setitem(sys.modules, "aiortc", fake_aiortc)
    monkeypatch.setitem(sys.modules, "aiohttp", types.SimpleNamespace(ClientSession=object))

    from providers import _webrtc_frames

    async def answer_request(offer: str) -> str:
        captured["offer"] = offer
        return "fake-answer"

    async def read_one():
        camera = _camera(CameraProtocol.ring, "ring://cam-1")
        frames = _webrtc_frames(camera, answer_request)
        frame = await frames.__anext__()
        await frames.aclose()
        return frame

    frame = asyncio.run(read_one())
    assert frame.shape == (2, 2, 3)
    assert captured["offer"] == "fake-offer"


def test_direct_adapter_decodes_on_a_worker_thread(monkeypatch):
    class FakeFrame:
        def to_ndarray(self, format: str):
            assert format == "bgr24"
            return np.ones((2, 2, 3), dtype=np.uint8)

    class FakePacket:
        def decode(self):
            return [FakeFrame()]

    class FakeContainer:
        streams = types.SimpleNamespace(video=[types.SimpleNamespace()])

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def demux(self, _stream):
            return [FakePacket()]

    monkeypatch.setitem(
        sys.modules,
        "av",
        types.SimpleNamespace(open=lambda _url, options: FakeContainer()),
    )

    async def read_one():
        frames = _direct_frames(_camera(CameraProtocol.rtsp, "rtsp://camera"))
        frame = await frames.__anext__()
        await frames.aclose()
        await asyncio.sleep(0)
        return frame

    frame = asyncio.run(read_one())
    assert frame.shape == (2, 2, 3)
