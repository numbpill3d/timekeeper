"""Regression tests for auth/profile API contracts."""

import os
from datetime import UTC, datetime
from types import SimpleNamespace

os.environ.setdefault("JWT_SECRET", "unit-test-secret-012345678901234567890123")

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from api.src.routes.events import _event_filters, count_events, list_events
from api.src.routes.persons import PersonUpdate, delete_person, list_persons
from api.src.routes.query import _check_rate_limit
from api.src.routes.users import (
    LoginRequest,
    ProfileUpdate,
    RegisterRequest,
    _check_auth_rate_limit,
    update_profile,
)


def test_auth_email_is_canonicalized_case_insensitively():
    assert RegisterRequest(
        email="Alice.Example@Example.COM", password="correct horse battery staple"
    ).email == "alice.example@example.com"


def test_auth_passwords_have_a_bounded_request_size():
    with pytest.raises(ValidationError):
        RegisterRequest(email="user@example.com", password="x" * 257)
    with pytest.raises(ValidationError):
        LoginRequest(email="user@example.com", password="x" * 257)


def test_person_retention_days_is_bounded_and_optional():
    assert PersonUpdate(retention_days=90).retention_days == 90
    assert PersonUpdate().model_dump(exclude_unset=True) == {}
    with pytest.raises(ValidationError):
        PersonUpdate(retention_days=0)
    with pytest.raises(ValidationError):
        PersonUpdate(retention_days=3651)


def test_event_search_is_scoped_and_escapes_wildcards():
    from api.src.routes.events import _event_filters

    where, params = _event_filters(
        "owner-1", None, None, None, None, "  blue_%  "
    )

    assert "ps.owner_id = $1" in where
    assert "os.owner_id = $1" in where
    assert params[-1] == r"%blue\_\%%"


def test_event_time_filters_normalize_naive_datetimes_to_utc():
    _, params = _event_filters(
        "owner-1",
        None,
        None,
        datetime(2026, 11, 13, 12, 0),
        datetime(2026, 11, 13, 13, 0, tzinfo=UTC),
    )
    assert params[1].tzinfo is UTC
    assert params[2].tzinfo is UTC


class _AuthRateRedis:
    def __init__(self, count: int = 0) -> None:
        self.initial_count = count
        self.counts: dict[str, int] = {}
        self.keys: list[str] = []
        self.expirations: list[tuple[str, int]] = []

    async def incr(self, key: str) -> int:
        self.keys.append(key)
        count = self.counts.setdefault(key, self.initial_count) + 1
        self.counts[key] = count
        return count

    async def expire(self, key: str, seconds: int) -> bool:
        self.expirations.append((key, seconds))
        return True


@pytest.mark.asyncio
async def test_auth_rate_limit_hashes_email_and_initializes_window():
    redis = _AuthRateRedis()
    request = SimpleNamespace(
        client=SimpleNamespace(host="192.0.2.10"),
        app=SimpleNamespace(state=SimpleNamespace(redis=redis)),
    )

    await _check_auth_rate_limit(request, "alice@example.com", "login")

    assert len(redis.keys) == 2
    assert all("alice@example.com" not in key for key in redis.keys)
    assert redis.expirations == [(key, 900) for key in redis.keys]


@pytest.mark.asyncio
async def test_auth_rate_limit_rejects_after_ten_attempts():
    redis = _AuthRateRedis(count=10)
    request = SimpleNamespace(
        client=SimpleNamespace(host="192.0.2.10"),
        app=SimpleNamespace(state=SimpleNamespace(redis=redis)),
    )

    with pytest.raises(HTTPException) as exc_info:
        await _check_auth_rate_limit(request, "alice@example.com", "login")
    assert exc_info.value.status_code == 429
    assert exc_info.value.headers["Retry-After"] == "900"
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


class _EventListDb:
    def __init__(self) -> None:
        self.sql = ""

    async def fetch(self, sql: str, *_params: object) -> list[dict]:
        self.sql = sql
        return []


@pytest.mark.asyncio
async def test_event_list_scopes_joined_identity_labels_to_owner():
    db = _EventListDb()
    await list_events({"sub": "owner-1"}, db)
    assert "p.owner_id = $1" in db.sql
    assert "o.owner_id = $1" in db.sql
    assert "COALESCE(o.label, o.category) AS object_label" in db.sql
    assert "ORDER BY e.timestamp DESC, e.id DESC" in db.sql


@pytest.mark.asyncio
async def test_event_detail_scopes_joined_identity_labels_to_owner():
    # The detail query shares the same tenant boundary, with the owner in $2.
    class DetailDb:
        sql = ""

        async def fetchrow(self, sql: str, *_params: object) -> None:
            self.sql = sql

    db = DetailDb()
    from api.src.routes.events import get_event

    with pytest.raises(HTTPException) as exc_info:
        # The route raises its normal 404 after recording the query.
        await get_event(
            "00000000-0000-0000-0000-000000000001",
            {"sub": "owner-1"},
            db,
        )
    assert exc_info.value.status_code == 404
    assert "p.owner_id = $2" in db.sql
    assert "o.owner_id = $2" in db.sql


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


@pytest.mark.asyncio
async def test_person_event_count_scopes_events_to_owner_cameras():
    class PersonListDb:
        sql = ""

        async def fetch(self, sql: str, _user_id: str) -> list[dict]:
            self.sql = sql
            return []

    db = PersonListDb()
    await list_persons({"sub": "owner-1"}, db)
    assert "e.camera_id IN (SELECT id FROM cameras WHERE owner_id = $1)" in db.sql


class _PersonDeleteTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


class _PersonDeleteDb:
    def __init__(self) -> None:
        self.queries: list[tuple[str, tuple[object, ...]]] = []

    def transaction(self) -> _PersonDeleteTransaction:
        return _PersonDeleteTransaction()

    async def fetchval(self, sql: str, *params: object) -> int:
        self.queries.append((sql, params))
        return 1

    async def execute(self, sql: str, *params: object) -> str:
        self.queries.append((sql, params))
        return "DELETE 1"


@pytest.mark.asyncio
async def test_person_delete_detaches_history_before_removing_identity():
    db = _PersonDeleteDb()
    person_id = "00000000-0000-0000-0000-000000000001"

    await delete_person(person_id, {"sub": "owner-1"}, db)

    statements = [query for query, _ in db.queries]
    assert "UPDATE detections SET person_id = NULL, association_confidence = NULL, association_method = NULL WHERE person_id = $1" in statements
    assert "UPDATE events SET person_id = NULL WHERE person_id = $1" in statements
    assert statements[-1] == "DELETE FROM persons WHERE id = $1"
