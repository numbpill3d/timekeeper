"""Pipedream Connect configuration and response-boundary tests."""

import os

os.environ.setdefault("JWT_SECRET", "unit-test-secret-012345678901234567890123")

import pytest
from fastapi import HTTPException

from api.src.routes import pipedream


def test_pipedream_requires_an_explicit_project(monkeypatch):
    monkeypatch.setattr(pipedream, "_PROJECT_ID", "")
    monkeypatch.setenv("PIPEDREAM_CLIENT_ID", "client")
    monkeypatch.setenv("PIPEDREAM_CLIENT_SECRET", "secret")
    with pytest.raises(HTTPException) as exc_info:
        pipedream._configured()
    assert exc_info.value.status_code == 503


def test_pipedream_rejects_invalid_environment(monkeypatch):
    monkeypatch.setattr(pipedream, "_PROJECT_ID", "proj_test")
    monkeypatch.setattr(pipedream, "_ENVIRONMENT", "staging")
    monkeypatch.setenv("PIPEDREAM_CLIENT_ID", "client")
    monkeypatch.setenv("PIPEDREAM_CLIENT_SECRET", "secret")
    with pytest.raises(HTTPException, match="environment is invalid"):
        pipedream._configured()


@pytest.mark.parametrize(
    "value",
    [
        "http://pipedream.com/connect",
        "javascript:alert(1)",
        "https://user:pass@pipedream.com/connect",
        "https://pipedream.com/connect#token",
        "https://attacker.example/connect",
        "not a URL",
    ],
)
def test_connect_link_must_be_safe_https(value):
    assert pipedream._validate_connect_link(value) is None


def test_connect_link_accepts_secure_https_url():
    assert (
        pipedream._validate_connect_link(" https://pipedream.com/connect ")
        == "https://pipedream.com/connect"
    )


def test_connect_link_accepts_pipedream_subdomains():
    assert pipedream._validate_connect_link(
        "https://connect.pipedream.com/connect"
    ) == "https://connect.pipedream.com/connect"


@pytest.mark.asyncio
async def test_pipedream_rejects_non_object_oauth_response(monkeypatch):
    monkeypatch.setattr(pipedream, "_PROJECT_ID", "proj_test")
    monkeypatch.setattr(pipedream, "_ENVIRONMENT", "production")
    monkeypatch.setenv("PIPEDREAM_CLIENT_ID", "client")
    monkeypatch.setenv("PIPEDREAM_CLIENT_SECRET", "secret")

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return ["not", "an", "object"]

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr(pipedream.httpx, "AsyncClient", lambda **_kwargs: Client())
    with pytest.raises(HTTPException) as exc_info:
        await pipedream.create_connect_token({"sub": "owner-1"})
    assert exc_info.value.status_code == 502


@pytest.mark.asyncio
async def test_pipedream_does_not_expose_connect_token_to_clients(monkeypatch):
    monkeypatch.setattr(pipedream, "_PROJECT_ID", "proj_test")
    monkeypatch.setattr(pipedream, "_ENVIRONMENT", "production")
    monkeypatch.setenv("PIPEDREAM_CLIENT_ID", "client")
    monkeypatch.setenv("PIPEDREAM_CLIENT_SECRET", "secret")

    class Response:
        def __init__(self, body):
            self.body = body

        def raise_for_status(self):
            return None

        def json(self):
            return self.body

    class Client:
        def __init__(self):
            self.responses = iter([
                Response({"access_token": "oauth-token"}),
                Response({
                    "token": "connect-token",
                    "connect_link_url": "https://pipedream.com/connect",
                    "expires_at": "2026-11-12T12:00:00Z",
                }),
            ])

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, *_args, **_kwargs):
            return next(self.responses)

    monkeypatch.setattr(pipedream.httpx, "AsyncClient", lambda **_kwargs: Client())
    result = await pipedream.create_connect_token({"sub": "owner-1"})
    assert result.connect_link_url == "https://pipedream.com/connect"
    assert not hasattr(result, "token")


@pytest.mark.asyncio
async def test_pipedream_rejects_malformed_expiry(monkeypatch):
    monkeypatch.setattr(pipedream, "_PROJECT_ID", "proj_test")
    monkeypatch.setattr(pipedream, "_ENVIRONMENT", "production")
    monkeypatch.setenv("PIPEDREAM_CLIENT_ID", "client")
    monkeypatch.setenv("PIPEDREAM_CLIENT_SECRET", "secret")

    class Response:
        def __init__(self, body):
            self.body = body

        def raise_for_status(self):
            return None

        def json(self):
            return self.body

    class Client:
        def __init__(self):
            self.responses = iter([
                Response({"access_token": "oauth-token"}),
                Response({
                    "connect_link_url": "https://pipedream.com/connect",
                    "expires_at": {"unexpected": "object"},
                }),
            ])

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, *_args, **_kwargs):
            return next(self.responses)

    monkeypatch.setattr(pipedream.httpx, "AsyncClient", lambda **_kwargs: Client())
    with pytest.raises(HTTPException) as exc_info:
        await pipedream.create_connect_token({"sub": "owner-1"})
    assert exc_info.value.status_code == 502
