"""Notification provider failure-boundary tests."""

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
