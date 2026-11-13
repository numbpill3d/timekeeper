"""Regression tests for auth/profile API contracts."""

import os
from datetime import UTC, datetime

os.environ.setdefault("JWT_SECRET", "unit-test-secret-012345678901234567890123")

import pytest

from api.src.routes.events import count_events
from api.src.routes.users import (
    LoginRequest,
    ProfileUpdate,
    RegisterRequest,
    update_profile,
)


def test_auth_email_is_canonicalized_case_insensitively():
    assert RegisterRequest(
        email="Alice.Example@Example.COM", password="correct horse battery staple"
    ).email == "alice.example@example.com"
    assert LoginRequest(
        email="ALICE.EXAMPLE@EXAMPLE.COM", password="correct horse battery staple"
    ).email == "alice.example@example.com"


class _ProfileDb:
    def __init__(self) -> None:
        self.updates: tuple[object, ...] | None = None

    async def execute(self, _sql: str, *params: object) -> None:
        self.updates = params

    async def fetchrow(self, _sql: str, _user_id: str) -> dict:
        return {
            "email": "alice.example@example.com",
            "subscription_tier": "home",
            "fcm_token": "token-2",
            "phone": "+15551234567",
            "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        }


@pytest.mark.asyncio
async def test_profile_update_returns_the_full_profile_contract():
    db = _ProfileDb()
    result = await update_profile(
        ProfileUpdate(fcm_token="token-2"),
        {"sub": "00000000-0000-0000-0000-000000000001"},
        db,
    )
    assert db.updates == (
        "00000000-0000-0000-0000-000000000001",
        "token-2",
    )
    assert result["email"] == "alice.example@example.com"
    assert result["tier"] == "home"
    assert result["fcm_token"] == "token-2"


class _EventCountDb:
    def __init__(self, count: int) -> None:
        self.count = count
        self.params: tuple[object, ...] | None = None

    async def fetchval(self, _sql: str, *params: object) -> int:
        self.params = params
        return self.count


@pytest.mark.asyncio
async def test_event_count_is_owner_scoped_and_preserves_time_filters():
    db = _EventCountDb(321)
    result = await count_events(
        {"sub": "owner-1"},
        db,
        since=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert result.count == 321
    assert db.params is not None
    assert db.params[0] == "owner-1"
    assert db.params[1] == datetime(2026, 1, 1, tzinfo=UTC)
