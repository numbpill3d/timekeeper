"""Tests for evidence-object boundary handling."""

import pytest

from api.src.media import object_key, safe_signed_clip_url


def test_object_key_normalizes_legacy_bucket_urls():
    assert object_key("http://minio:9000/omniscient-media/clips/a.jpg") == "clips/a.jpg"


@pytest.mark.parametrize("value", ["../secret", "clips/../../secret", "clips\\secret"])
def test_object_key_rejects_traversal(value):
    with pytest.raises(ValueError):
        object_key(value)


def test_object_key_rejects_foreign_urls():
    with pytest.raises(ValueError):
        object_key("https://example.test/omniscient-media/clips/a.jpg")


def test_safe_signed_clip_url_omits_invalid_legacy_keys():
    assert safe_signed_clip_url("https://example.test/foreign/clip.jpg") is None
