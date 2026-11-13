"""Smoke-test application startup imports that unit tests otherwise bypass."""

import os

os.environ.setdefault("JWT_SECRET", "test-secret-for-unit-tests-only-must-be-32c")

from api.src.main import app


def test_api_entrypoint_imports_with_runtime_dependencies():
    paths = {
        path
        for route in app.routes
        if (path := getattr(route, "path", None)) is not None
    }
    assert "/health" in paths
