"""Validation helpers for persisted person-embedding galleries."""

from __future__ import annotations

import numpy as np

EMBEDDING_DIM = 512


def parse_gallery_embedding(
    raw: object, *, dimension: int = EMBEDDING_DIM
) -> np.ndarray | None:
    """Parse and validate one pgvector value before gallery insertion."""
    try:
        values = [float(value) for value in str(raw).strip("[]").split(",")]
        embedding = np.asarray(values, dtype=np.float32)
    except (TypeError, ValueError):
        return None
    if embedding.ndim != 1 or embedding.size != dimension:
        return None
    if not np.isfinite(embedding).all():
        return None
    return embedding
