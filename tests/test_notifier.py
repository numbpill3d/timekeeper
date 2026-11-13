"""Notification provider failure-boundary tests."""

import notifier
import pytest
from notifier import _send_fcm_v1


@pytest.mark.asyncio
async def test_fcm_auth_provider_failure_is_non_fatal(monkeypatch):
    class ProviderRefreshError(Exception):
        pass

    def fail_to_refresh():
        raise ProviderRefreshError("credential refresh failed")

    monkeypatch.setattr("notifier._fcm_access_token", fail_to_refresh)
    monkeypatch.setattr("notifier._FCM_PROJECT_ID", "valid-project-123")

    assert await _send_fcm_v1("device-token", "title", "body") is False


@pytest.mark.asyncio
async def test_sms_delivery_uses_the_sync_provider_in_a_worker(monkeypatch):
    calls: list[tuple[str, str]] = []

    def send(to: str, message: str) -> None:
        calls.append((to, message))

    monkeypatch.setattr(notifier, "_send_sms_sync", send)

    assert await notifier._send_sms("+15551234567", "hello") is True
    assert calls == [("+15551234567", "hello")]
