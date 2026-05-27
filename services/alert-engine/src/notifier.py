"""
Multi-channel notification delivery.

Supported channels: push (FCM via legacy HTTP API), sms (Twilio).
Channels are selected per alert rule; delivery silently no-ops if the
required credentials are not configured in the environment.
"""

from __future__ import annotations

import logging
import os

import httpx

log = logging.getLogger(__name__)

_FCM_KEY = os.getenv("FCM_SERVER_KEY", "")
_TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
_TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
_TWILIO_FROM = os.getenv("TWILIO_FROM_NUMBER", "")

_FCM_URL = "https://fcm.googleapis.com/fcm/send"


async def deliver(
    channels: list[str],
    title: str,
    body: str,
    fcm_token: str | None = None,
    phone: str | None = None,
) -> list[str]:
    """Send notification over requested channels. Returns list of sent channels."""
    sent = []

    if "push" in channels and fcm_token and _FCM_KEY:
        ok = await _send_fcm(fcm_token, title, body)
        if ok:
            sent.append("push")

    if "sms" in channels and phone and _TWILIO_SID:
        ok = await _send_sms(phone, f"{title}: {body}")
        if ok:
            sent.append("sms")

    return sent


async def _send_fcm(token: str, title: str, body: str) -> bool:
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
    except Exception as exc:
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
