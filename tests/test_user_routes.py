"""Regression tests for auth/profile API contracts."""

import os
from datetime import UTC, datetime
from types import SimpleNamespace

os.environ.setdefault("JWT_SECRET", "unit-test-secret-012345678901234567890123")

import pytest

from api.src.routes.events import count_events
from api.src.routes.persons import list_persons
from api.src.routes.query import _check_rate_limit
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


class _TierDb:
    def __init__(self, tier: str | None) -> None:
        self.tier = tier

    async def fetchval(self, _sql: str, _user_id: str) -> str | None:
        return self.tier


class _RateLimitRedis:
    def __init__(self) -> None:
        self.increments = 0

    async def incr(self, _key: str) -> int:
        self.increments += 1
        return self.increments

    async def expire(self, _key: str, _seconds: int) -> bool:
        return True


@pytest.mark.asyncio
async def test_query_rate_limit_uses_current_database_tier():
    redis = _RateLimitRedis()
    db = _TierDb("home")
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(db=db, redis=redis))
    )
    user = {"sub": "owner-1", "tier": "free"}

    await _check_rate_limit(user, request)
    assert redis.increments == 0

    db.tier = "free"
    await _check_rate_limit(user, request)
    assert redis.increments == 1


class _PersonsDb:
    async def fetch(self, _sql: str, _user_id: str) -> list[dict]:
        return [{
            "id": "00000000-0000-0000-0000-000000000001",
            "label": "Unknown A1B2C3",
            "is_known": False,
            "appearance_tags": None,
            "retention_days": 30,
            "last_seen_at": None,
            "created_at": datetime(2026, 1, 1, tzinfo=UTC),
            "event_count": 0,
        }]


@pytest.mark.asyncio
async def test_person_list_normalizes_legacy_null_appearance_tags():
    result = await list_persons(
        {"sub": "owner-1"},
        _PersonsDb(),
    )
    # The SQL COALESCE is the database-side contract; this fixture models a
    # legacy row so the response shape remains explicit in the test.
    assert result[0].appearance_tags == []
