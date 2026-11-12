"""Boundary tests for event-processor frame and object paths."""

import pytest

from storage import object_key


def test_object_key_rejects_traversal():
    with pytest.raises(ValueError):
        object_key("clips/../../private.jpg")


def test_object_key_rejects_foreign_url():
    with pytest.raises(ValueError):
        object_key("https://example.test/omniscient-media/clips/a.jpg")
