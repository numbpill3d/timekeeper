"""Boundary tests for event-processor frame and object paths."""

import pytest

from storage import cleanup_frame, object_key


def test_object_key_rejects_traversal():
    with pytest.raises(ValueError):
        object_key("clips/../../private.jpg")


def test_object_key_rejects_foreign_url():
    with pytest.raises(ValueError):
        object_key("https://example.test/omniscient-media/clips/a.jpg")


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
