"""
OSNet person re-identification via torchreid.

Extracts 512-dim appearance embeddings for person crops and
matches them across camera views using cosine similarity.
Enables cross-camera identity persistence ("same person, different camera").
"""

from __future__ import annotations

import logging

import numpy as np
import torch

try:
    import torchreid

    _TORCHREID_AVAILABLE = True
except ImportError:
    _TORCHREID_AVAILABLE = False
    logging.getLogger(__name__).warning(
        "torchreid not available — ReID disabled; "
        "persons will not be matched across cameras"
    )

REID_THRESHOLD = 0.7  # cosine similarity threshold for a positive match
log = logging.getLogger(__name__)


class ReIDModel:
    def __init__(
        self,
        model_name: str = "osnet_x1_0",
        device: str | None = None,
    ) -> None:
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self._model = None

        if _TORCHREID_AVAILABLE:
            try:
                self._model = torchreid.models.build_model(
                    name=model_name,
                    num_classes=1000,
                    pretrained=True,
                )
                self._model.eval()
                self._model.to(self.device)
            except Exception:
                # ReID is an optional enhancement. A missing or unavailable
                # weight file must not take the entire vision worker down.
                log.exception("ReID model unavailable; disabling cross-camera matching")
                self._model = None

    def extract(self, crop: np.ndarray) -> np.ndarray | None:
        """Extract a 512-dim L2-normalized embedding from a person crop (BGR)."""
        if self._model is None or crop.size == 0:
            return None

        import torchvision.transforms as T
        from PIL import Image

        transform = T.Compose([
            T.Resize((256, 128)),
            T.ToTensor(),
            T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ])

        img = Image.fromarray(crop[..., ::-1])  # BGR->RGB
        tensor = transform(img).unsqueeze(0).to(self.device)

        with torch.no_grad():
            feat = self._model(tensor)
            feat = torch.nn.functional.normalize(feat, dim=1)

        return feat.squeeze(0).cpu().numpy()

    @staticmethod
    def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        return float(np.dot(a, b))

    def match(
        self,
        query: np.ndarray,
        gallery: list[tuple[str, np.ndarray]],
    ) -> tuple[str, float] | None:
        """Find the best match for query in gallery.

        gallery: list of (person_id_str, embedding).
        Returns (person_id, similarity) if above threshold, else None.
        """
        best_id, best_sim = None, REID_THRESHOLD
        for pid, emb in gallery:
            sim = self.cosine_similarity(query, emb)
            if sim > best_sim:
                best_id, best_sim = pid, sim
        return (best_id, best_sim) if best_id else None
