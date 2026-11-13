"""Regression tests for vision gallery input validation."""

import numpy as np
from gallery import parse_gallery_embedding, remove_person_from_gallery


def test_gallery_embedding_accepts_valid_pgvector_text():
    embedding = parse_gallery_embedding("[" + ",".join(["0.25"] * 512) + "]")

    assert isinstance(embedding, np.ndarray)
    assert embedding.shape == (512,)
    assert np.allclose(embedding, 0.25)


def test_gallery_embedding_skips_wrong_dimension_and_malformed_values():
    assert parse_gallery_embedding("[0.1, 0.2]") is None
    assert parse_gallery_embedding("not-a-vector") is None
    assert parse_gallery_embedding("[0.1, nope]") is None


def test_gallery_embedding_skips_non_finite_values():
    assert parse_gallery_embedding("[" + ",".join(["nan"] * 512) + "]") is None
    assert parse_gallery_embedding("[" + ",".join(["inf"] * 512) + "]") is None


def test_deleted_person_is_removed_from_all_owner_galleries():
    embedding = np.zeros(512, dtype=np.float32)
    galleries = {
        "owner-a": [("person-1", embedding), ("person-2", embedding)],
        "owner-b": [("person-1", embedding)],
    }

    remove_person_from_gallery(galleries, "person-1")

    assert [person_id for person_id, _ in galleries["owner-a"]] == ["person-2"]
    assert galleries["owner-b"] == []
