"""Camera provider adapters.

Direct streams use PyAV. Cloud providers use their authenticated WebRTC/WHEP
session APIs and yield decoded frames through the same interface, so the
vision pipeline remains provider-agnostic. Credentials are read from the
environment or an explicitly named environment variable; they are never
stored in ``provider_config``.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any
from urllib.parse import urlparse

import numpy as np

from omniscient_shared.models.camera import Camera, CameraProtocol


class ProviderError(RuntimeError):
    """A provider could not produce a usable video stream."""


_ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")


def _safe_provider_env_name(value: str, provider: str) -> str:
    """Prevent camera config from selecting unrelated process secrets."""
    name = value.strip()
    prefix = f"{provider.upper()}_"
    if not _ENV_NAME_RE.fullmatch(name) or not name.startswith(prefix):
        raise ProviderError(
            f"{provider} access_token_env must be an uppercase {prefix}* name"
        )
    return name


def _control_endpoint(value: str, label: str) -> str:
    parsed = urlparse(value)
    if parsed.username or parsed.password or not parsed.hostname:
        raise ProviderError(f"{label} must be a URL without embedded credentials")
    if parsed.scheme == "https":
        return value
    if parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}:
        return value
    raise ProviderError(f"{label} must use HTTPS (or loopback HTTP for a local bridge)")


async def _direct_frames(camera: Camera) -> AsyncIterator[np.ndarray]:
    try:
        import av
    except ImportError as exc:
        raise ProviderError("direct stream support requires PyAV") from exc

    options = {"rtsp_transport": "tcp", "stimeout": "5000000"}
    if camera.protocol.value not in {"rtsp", "onvif"}:
        options = {}
    try:
        with av.open(camera.stream_url, options=options) as container:
            stream = container.streams.video[0]
            stream.thread_type = "AUTO"
            for packet in container.demux(stream):
                for frame in packet.decode():
                    yield frame.to_ndarray(format="bgr24")
    except Exception as exc:
        raise ProviderError(f"direct stream failed for {camera.name}: {exc}") from exc


def _token(config: dict[str, Any], default_env: str) -> str:
    env_name = str(config.get("access_token_env", default_env))
    token = os.getenv(env_name, "").strip()
    if token:
        return token

    # Docker/Kubernetes secret injection convention. The file path is supplied
    # through the environment, never persisted in provider_config or logs.
    file_path = os.getenv(f"{env_name}_FILE", "").strip()
    if not file_path:
        return ""
    try:
        with open(file_path, encoding="utf-8") as secret_file:
            return secret_file.read().strip()
    except OSError as exc:
        raise ProviderError(
            f"credential file configured by {env_name}_FILE is unavailable"
        ) from exc


class _OAuthCredentials:
    """Resolve a static token or refresh it in memory when configured."""

    def __init__(self, config: dict[str, Any], provider: str) -> None:
        prefix = provider.upper()
        self.config = config
        self.provider = provider
        self.access_env = _safe_provider_env_name(
            str(config.get("access_token_env", f"{prefix}_ACCESS_TOKEN")),
            provider,
        )
        self.refresh_env = f"{prefix}_REFRESH_TOKEN"
        self.token_url = str(
            config.get("token_url") or os.getenv(f"{prefix}_TOKEN_URL", "")
        )
        if self.token_url:
            self.token_url = _control_endpoint(self.token_url, "token endpoint")
        self._access_token = ""
        self._expires_at = 0.0

    async def get(self, *, force_refresh: bool = False) -> str:
        direct = _token(self.config, self.access_env)
        refresh = _token({}, self.refresh_env)
        if direct and not force_refresh:
            return direct
        if not self.token_url or not refresh:
            if direct:
                return direct
            raise ProviderError(
                f"{self.provider} needs {self.access_env}, or {self.refresh_env} "
                f"with {self.refresh_env.replace('_TOKEN', '_TOKEN_URL')}"
            )
        if self._access_token and time.monotonic() < self._expires_at and not force_refresh:
            return self._access_token

        client_id = _token({}, f"{self.provider.upper()}_CLIENT_ID")
        client_secret = _token({}, f"{self.provider.upper()}_CLIENT_SECRET")
        if not client_id or not client_secret:
            raise ProviderError(
                f"{self.provider} refresh requires provider client credentials"
            )
        try:
            from aiohttp import ClientSession

            payload = {
                "grant_type": "refresh_token",
                "refresh_token": refresh,
                "client_id": client_id,
                "client_secret": client_secret,
            }
            async with ClientSession() as session:
                async with session.post(self.token_url, data=payload) as response:
                    body = await response.text()
                    if response.status >= 400:
                        raise ProviderError(
                            f"{self.provider} token refresh failed ({response.status})"
                        )
                    result = json.loads(body)
            token = str(result.get("access_token", "")).strip()
            if not token:
                raise ProviderError(f"{self.provider} refresh returned no access token")
            self._access_token = token
            self._expires_at = time.monotonic() + max(
                60, int(result.get("expires_in", 3600)) - 60
            )
            return token
        except ProviderError:
            raise
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise ProviderError(f"{self.provider} token refresh response was invalid") from exc


def _device_id(camera: Camera) -> str:
    value = camera.stream_url
    for prefix in ("ring://", "nest://", "arlo://", "wyze://"):
        if value.startswith(prefix):
            return value.removeprefix(prefix)
    return value


def _provider_endpoint(camera: Camera) -> tuple[str, str]:
    """Return (provider, endpoint) for a configured WHEP-compatible source."""
    config = camera.provider_config
    provider = camera.protocol.value
    explicit = config.get("whep_url")
    if explicit:
        return provider, _control_endpoint(str(explicit), "WHEP endpoint")

    device_id = _device_id(camera)
    env_template = os.getenv(f"{provider.upper()}_WHEP_URL_TEMPLATE", "")
    if env_template:
        return provider, _control_endpoint(
            env_template.format(device_id=device_id), "WHEP endpoint"
        )

    defaults = {
        # Ring's official developer experience exposes a WHEP live-video
        # session endpoint; the account must be linked and authorized first.
        "ring": "https://api.amazonvision.com/v1/devices/{device_id}/media/streaming/whep/sessions",
    }
    template = defaults.get(provider)
    if template:
        return provider, _control_endpoint(
            template.format(device_id=device_id), "WHEP endpoint"
        )
    raise ProviderError(
        f"{provider} camera {camera.name} needs provider_config.whep_url or "
        f"{provider.upper()}_WHEP_URL_TEMPLATE"
    )


def _configured_direct_camera(camera: Camera) -> Camera | None:
    """Use a local RTSP/HTTP bridge when a cloud provider has no native API."""
    direct_url = camera.provider_config.get("rtsp_url") or camera.provider_config.get(
        "stream_url"
    )
    if not direct_url:
        return None
    return camera.model_copy(
        update={"stream_url": str(direct_url), "protocol": CameraProtocol.rtsp}
    )


async def _webrtc_frames(
    camera: Camera,
    answer_request: Callable[[str], Awaitable[str]],
    *,
    include_audio: bool = False,
    include_data: bool = False,
) -> AsyncIterator[np.ndarray]:
    """Create one receive-only WebRTC session and yield video frames."""
    try:
        from aiohttp import ClientSession
        from aiortc import RTCPeerConnection, RTCSessionDescription
    except ImportError as exc:
        raise ProviderError(
            "cloud camera support requires aiohttp and aiortc"
        ) from exc

    pc = RTCPeerConnection()
    track_future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()

    @pc.on("track")
    def on_track(track: Any) -> None:
        if track.kind == "video" and not track_future.done():
            track_future.set_result(track)

    try:
        # Nest's CameraLiveStream contract requires audio, video, and a data
        # channel in this order. Ring's WHEP live stream is video-only.
        if include_audio:
            pc.addTransceiver("audio", direction="recvonly")
        pc.addTransceiver("video", direction="recvonly")
        if include_data:
            pc.createDataChannel("timekeeper")
        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)
        answer_sdp = await answer_request(pc.localDescription.sdp)
        await pc.setRemoteDescription(
            RTCSessionDescription(sdp=answer_sdp, type="answer")
        )
        track = await asyncio.wait_for(track_future, timeout=30)
        while True:
            frame = await track.recv()
            yield frame.to_ndarray(format="bgr24")
    except Exception as exc:
        if isinstance(exc, ProviderError):
            raise
        raise ProviderError(f"WebRTC session failed for {camera.name}: {exc}") from exc
    finally:
        await pc.close()


async def _whep_frames(camera: Camera) -> AsyncIterator[np.ndarray]:
    provider, endpoint = _provider_endpoint(camera)
    config = camera.provider_config
    credentials = _OAuthCredentials(config, provider)
    await credentials.get()

    async def answer_request(offer_sdp: str) -> str:
        from aiohttp import ClientSession

        async def request(token: str) -> tuple[int, str, str]:
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/sdp",
                "Accept": "application/sdp, application/json",
            }
            async with ClientSession() as session:
                async with session.post(endpoint, data=offer_sdp, headers=headers) as response:
                    return response.status, response.content_type, await response.text()

        token = await credentials.get()
        status, content_type, body = await request(token)
        if status == 401:
            status, content_type, body = await request(
                await credentials.get(force_refresh=True)
            )
        if status >= 400:
            raise ProviderError(f"{provider} WHEP error {status}")
        if content_type == "application/json":
            payload = json.loads(body)
            body = payload.get("answerSdp") or payload.get("sdp", "")
        if not body.strip():
            raise ProviderError(f"{provider} returned an empty WebRTC answer")
        return body

    async for frame in _webrtc_frames(camera, answer_request):
        yield frame


async def _nest_frames(camera: Camera) -> AsyncIterator[np.ndarray]:
    """Google Nest Device Access adapter using GenerateWebRtcStream."""
    config = camera.provider_config
    credentials = _OAuthCredentials(config, "nest")
    project_id = config.get("project_id") or os.getenv("NEST_PROJECT_ID", "")
    device_id = _device_id(camera)
    if not project_id:
        raise ProviderError(
            "Nest requires NEST_ACCESS_TOKEN, NEST_PROJECT_ID, and a nest://device-id source"
        )
    await credentials.get()

    api_base = str(config.get("api_base", "https://smartdevicemanagement.googleapis.com/v1"))
    command_url = config.get("command_url") or (
        f"{api_base}/enterprises/{project_id}/devices/{device_id}:executeCommand"
    )

    async def answer_request(offer_sdp: str) -> str:
        from aiohttp import ClientSession

        payload = {
            "command": "sdm.devices.commands.CameraLiveStream.GenerateWebRtcStream",
            "params": {"offerSdp": offer_sdp},
        }
        async def request(token: str) -> tuple[int, str]:
            headers = {"Authorization": f"Bearer {token}"}
            async with ClientSession() as session:
                async with session.post(command_url, json=payload, headers=headers) as response:
                    return response.status, await response.text()

        status, body = await request(await credentials.get())
        if status == 401:
            status, body = await request(await credentials.get(force_refresh=True))
        if status >= 400:
            raise ProviderError(f"Nest API error {status}")
        try:
            answer = json.loads(body)["results"]["answerSdp"]
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ProviderError("Nest response did not contain answerSdp") from exc
        return answer

    async for frame in _webrtc_frames(
        camera, answer_request, include_audio=True, include_data=True
    ):
        yield frame


async def frames_for(camera: Camera) -> AsyncIterator[np.ndarray]:
    """Yield decoded BGR frames for any configured camera source."""
    if camera.protocol in {
        CameraProtocol.ring,
        CameraProtocol.arlo,
        CameraProtocol.wyze,
    }:
        direct_camera = _configured_direct_camera(camera)
        if direct_camera:
            async for frame in _direct_frames(direct_camera):
                yield frame
            return
        async for frame in _whep_frames(camera):
            yield frame
        return
    if camera.protocol == CameraProtocol.nest:
        async for frame in _nest_frames(camera):
            yield frame
        return
    async for frame in _direct_frames(camera):
        yield frame
