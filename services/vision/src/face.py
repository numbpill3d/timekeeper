"""Optional FaceNet face embedding and matching."""

from __future__ import annotations

import logging

import numpy as np

log = logging.getLogger(__name__)
FACE_THRESHOLD = 0.72


class FaceModel:
    """Extract 512-dim FaceNet embeddings when the model is available.

    The vision service remains operational without the optional model weights;
    callers then use appearance ReID and preserve the lower-confidence path.
    """

    def __init__(self, device: str | None = None) -> None:
        self._detector = None
        self._model = None
        try:
            import torch
            from facenet_pytorch import MTCNN, InceptionResnetV1

            target = device or ("cuda" if torch.cuda.is_available() else "cpu")
            self._detector = MTCNN(
                image_size=160,
                margin=14,
                keep_all=False,
                device=target,
                post_process=True,
            )
            self._model = InceptionResnetV1(
                pretrained="vggface2", classify=False
            ).eval().to(target)
            log.info("FaceNet recognition enabled on %s", target)
        except Exception as exc:  # noqa: BLE001 - optional model initialization
            log.warning(
                "FaceNet unavailable (%s); using appearance ReID only",
                type(exc).__name__,
            )

    def extract(self, crop: np.ndarray) -> np.ndarray | None:
        if self._detector is None or self._model is None or crop.size == 0:
            return None
        import torch
        from PIL import Image

        face = self._detector(Image.fromarray(crop[..., ::-1]))
        if face is None:
            return None
        with torch.no_grad():
            embedding = self._model(face.unsqueeze(0))
            embedding = torch.nn.functional.normalize(embedding, dim=1)
        return embedding.squeeze(0).cpu().numpy().astype(np.float32)

    @staticmethod
    def match(
        query: np.ndarray,
        gallery: list[tuple[str, np.ndarray]],
    ) -> tuple[str, float] | None:
        best_id, best_similarity = None, FACE_THRESHOLD
        for person_id, embedding in gallery:
            similarity = float(np.dot(query, embedding))
            if similarity > best_similarity:
                best_id, best_similarity = person_id, similarity
        return (best_id, best_similarity) if best_id else None
