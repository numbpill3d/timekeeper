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
