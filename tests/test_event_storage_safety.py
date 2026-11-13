"""Boundary tests for event-processor frame and object paths."""

import importlib.util
import sys
import types
from pathlib import Path

import pytest
from storage import cleanup_frame, object_key


def _load_event_processor_db():
    """Load the hyphenated service package without colliding with query db.py."""
    package_name = "_timekeeper_event_processor"
    source_dir = Path(__file__).parents[1] / "services" / "event-processor" / "src"
    package = types.ModuleType(package_name)
    package.__path__ = [str(source_dir)]
    sys.modules[package_name] = package
    module_name = f"{package_name}.db"
    spec = importlib.util.spec_from_file_location(module_name, source_dir / "db.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


event_db = _load_event_processor_db()
purge_expired_events = event_db.purge_expired_events
purge_expired_detections = event_db.purge_expired_detections


def test_object_key_rejects_traversal():
    with pytest.raises(ValueError):
        object_key("clips/../../private.jpg")


@pytest.mark.parametrize("value", ["private/secret", "secret.jpg"])
def test_object_key_rejects_non_clip_namespaces(value):
    with pytest.raises(ValueError):
        object_key(value)


def test_object_key_rejects_foreign_url():
    with pytest.raises(ValueError):
        object_key("https://example.test/omniscient-media/clips/a.jpg")


def test_clip_upload_retries_transient_storage_failure(monkeypatch):
    attempts = 0
    sleeps: list[int] = []

    def fake_upload(_path: str, _bucket: str, _key: str) -> None:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise OSError("storage is starting")

    monkeypatch.setattr(event_db._s3, "upload_file", fake_upload)
    monkeypatch.setattr(event_db, "_ensure_bucket", lambda: None)
    monkeypatch.setattr(event_db.time, "sleep", sleeps.append)

    assert event_db._upload_sync("/tmp/frame.jpg", "clips/event.jpg") == "clips/event.jpg"
    assert attempts == 3
    assert sleeps == [1, 2]


def test_consumed_frame_cleanup_stays_inside_frame_root(tmp_path, monkeypatch):
    frame = tmp_path / "frame.jpg"
    frame.write_bytes(b"frame")
    monkeypatch.setattr("storage._FRAME_ROOT", tmp_path.resolve())

    cleanup_frame(str(frame))
    assert not frame.exists()


def test_consumed_frame_cleanup_rejects_sibling_path(tmp_path, monkeypatch):
    root = tmp_path / "frames"
    sibling = tmp_path / "frames-archive" / "frame.jpg"
    sibling.parent.mkdir()
    sibling.write_bytes(b"keep")
    monkeypatch.setattr("storage._FRAME_ROOT", root.resolve())

    cleanup_frame(str(sibling))
    assert sibling.exists()


@pytest.mark.asyncio
async def test_retention_deletes_alert_deliveries_with_expired_events():
    class Transaction:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

    class Db:
        def __init__(self):
            self.statements: list[str] = []
            self.fetch_sql = ""

        async def fetch(self, sql: str, *_params: object):
            self.fetch_sql = sql
            return [{"id": "event-1", "clip_path": None}]

        def transaction(self):
            return Transaction()

        async def execute(self, sql: str, *_params: object):
            self.statements.append(sql)

    db = Db()
    deleted = await purge_expired_events(db)

    assert deleted == 1
    assert "c.retention_days" in db.fetch_sql
    assert "DELETE FROM alert_deliveries" in db.statements[0]
    assert "DELETE FROM event_annotations" in db.statements[1]
    assert "DELETE FROM events" in db.statements[2]


@pytest.mark.asyncio
async def test_retention_deletes_a_bounded_batch_of_raw_detections():
    class Db:
        sql = ""

        async def execute(self, sql: str, *_params: object):
            self.sql = sql
            return "DELETE 37"

    db = Db()
    assert await purge_expired_detections(db) == 37
    assert "c.retention_days" in db.sql
