"""Tests for evidence-object boundary handling."""

import pytest

from api.src.media import delete_clip_objects, object_key, safe_signed_clip_url


def test_object_key_normalizes_legacy_bucket_urls():
    assert object_key("http://minio:9000/omniscient-media/clips/a.jpg") == "clips/a.jpg"


@pytest.mark.parametrize(
    "value",
    ["../secret", "clips/../../secret", "clips\\secret", "private/secret", "secret.jpg"],
)
def test_object_key_rejects_traversal(value):
    with pytest.raises(ValueError):
        object_key(value)


def test_object_key_rejects_foreign_urls():
    with pytest.raises(ValueError):
        object_key("https://example.test/omniscient-media/clips/a.jpg")


def test_safe_signed_clip_url_omits_invalid_legacy_keys():
    assert safe_signed_clip_url("https://example.test/foreign/clip.jpg") is None


@pytest.mark.asyncio
async def test_delete_clip_objects_deduplicates_and_normalizes_keys(monkeypatch):
    deleted: list[str] = []

    def fake_delete(keys: list[str]) -> None:
        deleted.extend(keys)

    monkeypatch.setattr("api.src.media._delete_keys_sync", fake_delete)
    await delete_clip_objects([
        "clips/a.jpg",
        "clips/a.jpg",
        "http://minio:9000/omniscient-media/clips/b.jpg",
        "https://example.test/clip.jpg",
    ])

    assert deleted == ["clips/a.jpg", "clips/b.jpg"]
