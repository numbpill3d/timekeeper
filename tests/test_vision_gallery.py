"""Regression tests for vision gallery input validation."""

import numpy as np
from gallery import parse_gallery_embedding


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
