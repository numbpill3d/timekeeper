"""Validation helpers for persisted person-embedding galleries."""

from __future__ import annotations

import numpy as np

EMBEDDING_DIM = 512


def validate_embedding(
    raw: object, *, dimension: int = EMBEDDING_DIM
) -> np.ndarray | None:
    """Return a finite, one-dimensional embedding with the expected size."""
    try:
        embedding = np.asarray(raw, dtype=np.float32)
    except (TypeError, ValueError):
        return None
    if embedding.ndim != 1 or embedding.size != dimension:
        return None
    if not np.isfinite(embedding).all():
        return None
    return embedding


def remove_person_from_gallery(
    gallery: dict[str, list[tuple[str, np.ndarray]]], person_id: str
) -> None:
    """Remove one deleted identity from every owner-scoped gallery."""
    for owner_id, entries in gallery.items():
        gallery[owner_id] = [
            (candidate_id, embedding)
            for candidate_id, embedding in entries
            if candidate_id != person_id
        ]


def parse_gallery_embedding(
    raw: object, *, dimension: int = EMBEDDING_DIM
) -> np.ndarray | None:
    """Parse and validate one pgvector value before gallery insertion."""
    try:
        values = [float(value) for value in str(raw).strip("[]").split(",")]
        embedding = np.asarray(values, dtype=np.float32)
    except (TypeError, ValueError):
        return None
    return validate_embedding(embedding, dimension=dimension)
