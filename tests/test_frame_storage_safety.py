"""Boundary tests for frames dropped before downstream publication."""

from services.vision.src import frame_storage


def test_unpublished_frame_cleanup_removes_only_files_inside_root(tmp_path, monkeypatch):
    root = tmp_path / "frames"
    root.mkdir()
    frame = root / "frame.jpg"
    frame.write_bytes(b"frame")
    monkeypatch.setattr(frame_storage, "_FRAME_ROOT", root.resolve())

    frame_storage.cleanup_unpublished_frame(str(frame))

    assert not frame.exists()


def test_unpublished_frame_cleanup_rejects_sibling_path(tmp_path, monkeypatch):
    root = tmp_path / "frames"
    sibling = tmp_path / "frames-archive" / "frame.jpg"
    sibling.parent.mkdir()
    sibling.write_bytes(b"keep")
    monkeypatch.setattr(frame_storage, "_FRAME_ROOT", root.resolve())

    frame_storage.cleanup_unpublished_frame(str(sibling))

    assert sibling.exists()
