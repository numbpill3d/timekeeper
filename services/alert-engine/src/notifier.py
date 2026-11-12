"""
Multi-channel notification delivery.

Supported channels: push (FCM HTTP v1, with a legacy fallback), sms (Twilio).
Channels are selected per alert rule; delivery silently no-ops if the
required credentials are not configured in the environment.
"""

from __future__ import annotations

import logging
import os
import asyncio
import json
import re

import httpx

log = logging.getLogger(__name__)

_FCM_KEY = os.getenv("FCM_SERVER_KEY", "")
_FCM_PROJECT_ID = os.getenv("FCM_PROJECT_ID", "").strip()
_FCM_SERVICE_ACCOUNT_FILE = os.getenv("FCM_SERVICE_ACCOUNT_FILE", "").strip()
_FCM_SERVICE_ACCOUNT_JSON = os.getenv("FCM_SERVICE_ACCOUNT_JSON", "").strip()
_TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
_TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
_TWILIO_FROM = os.getenv("TWILIO_FROM_NUMBER", "")

_FCM_URL = "https://fcm.googleapis.com/fcm/send"
_FCM_V1_PROJECT_RE = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")


async def deliver(
    channels: list[str],
    title: str,
    body: str,
    fcm_token: str | None = None,
    phone: str | None = None,
) -> list[str]:
    """Send notification over requested channels. Returns list of sent channels."""
    sent = []

    if "push" in channels and fcm_token and (
        _FCM_KEY or (_FCM_PROJECT_ID and (_FCM_SERVICE_ACCOUNT_FILE or _FCM_SERVICE_ACCOUNT_JSON))
    ):
        ok = await _send_fcm(fcm_token, title, body)
        if ok:
            sent.append("push")

    if "sms" in channels and phone and _TWILIO_SID:
        ok = await _send_sms(phone, f"{title}: {body}")
        if ok:
            sent.append("sms")

    return sent


async def _send_fcm(token: str, title: str, body: str) -> bool:
    if _FCM_PROJECT_ID and (_FCM_SERVICE_ACCOUNT_FILE or _FCM_SERVICE_ACCOUNT_JSON):
        return await _send_fcm_v1(token, title, body)
    log.warning("FCM_SERVER_KEY uses the legacy API; configure FCM HTTP v1 credentials")
    return await _send_fcm_legacy(token, title, body)


async def _send_fcm_v1(token: str, title: str, body: str) -> bool:
    if not _FCM_V1_PROJECT_RE.fullmatch(_FCM_PROJECT_ID):
        log.error("FCM_PROJECT_ID is invalid; push delivery disabled")
        return False
    try:
        access_token = await asyncio.to_thread(_fcm_access_token)
    except Exception as exc:
        log.warning("FCM credential setup failed: %s", exc)
        return False
    payload = {
        "message": {
            "token": token,
            "notification": {"title": title, "body": body},
            "android": {"priority": "high"},
        }
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"https://fcm.googleapis.com/v1/projects/{_FCM_PROJECT_ID}/messages:send",
                json=payload,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            return 200 <= response.status_code < 300
    except httpx.HTTPError as exc:
        log.warning("FCM HTTP v1 delivery failed: %s", exc)
        return False


def _fcm_access_token() -> str:
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account

    if _FCM_SERVICE_ACCOUNT_FILE:
        credentials = service_account.Credentials.from_service_account_file(
            _FCM_SERVICE_ACCOUNT_FILE,
            scopes=["https://www.googleapis.com/auth/firebase.messaging"],
        )
    else:
        info = json.loads(_FCM_SERVICE_ACCOUNT_JSON)
        credentials = service_account.Credentials.from_service_account_info(
            info,
            scopes=["https://www.googleapis.com/auth/firebase.messaging"],
        )
    credentials.refresh(Request())
    if not credentials.token:
        raise RuntimeError("FCM credentials returned no access token")
    return credentials.token


async def _send_fcm_legacy(token: str, title: str, body: str) -> bool:
    payload = {
        "to": token,
        "notification": {"title": title, "body": body},
        "priority": "high",
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.post(
                _FCM_URL,
                json=payload,
                headers={
                    "Authorization": f"key={_FCM_KEY}",
                    "Content-Type": "application/json",
                },
            )
            return r.status_code == 200
    except httpx.HTTPError as exc:
        log.warning("fcm delivery failed: %s", exc)
        return False


async def _send_sms(to: str, message: str) -> bool:
    try:
        from twilio.rest import Client

        client = Client(_TWILIO_SID, _TWILIO_TOKEN)
        client.messages.create(to=to, from_=_TWILIO_FROM, body=message)
        return True
    except Exception as exc:
        log.warning("sms delivery failed: %s", exc)
        return False
