"""Face matching behavior does not require downloading model weights."""

import numpy as np
from face import FACE_THRESHOLD, FaceModel


def test_face_gallery_uses_cosine_threshold():
    query = np.array([1.0, 0.0], dtype=np.float32)
    gallery = [
        ("wrong", np.array([0.0, 1.0], dtype=np.float32)),
        ("right", np.array([1.0, 0.0], dtype=np.float32)),
    ]
    assert FaceModel.match(query, gallery) == ("right", 1.0)
    assert FaceModel.match(
        np.array([-1.0, 0.0], dtype=np.float32), gallery
    ) is None
    assert FACE_THRESHOLD > 0.5
