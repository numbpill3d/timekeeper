"""Frame-local person/object association.

The association is deliberately geometric and explainable. Re-identification
supplies the person's stable ID; this module only decides whether an object is
being carried/handled by that person in the same frame. It never guesses an
identity when the boxes do not support the relationship.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot
from uuid import UUID


@dataclass(frozen=True)
class PersonCandidate:
    person_id: UUID
    bbox: tuple[float, float, float, float]
    detection_confidence: float


@dataclass(frozen=True)
class Association:
    person_id: UUID
    confidence: float
    method: str = "person_object_proximity"


def associate_person(
    object_bbox: tuple[float, float, float, float],
    candidates: list[PersonCandidate],
    threshold: float = 0.55,
) -> Association | None:
    """Return the strongest supported person/object association.

    An object whose center is inside an expanded person box is treated as
    carried/handled. Near-but-outside boxes can associate only when the object
    is very close to the person's lower body/hand area. Scores are bounded and
    multiplied by the detector confidence so low-quality detections remain
    visibly uncertain downstream.
    """
    ox = (object_bbox[0] + object_bbox[2]) / 2
    oy = (object_bbox[1] + object_bbox[3]) / 2
    best: Association | None = None

    for candidate in candidates:
        x1, y1, x2, y2 = candidate.bbox
        width = max(x2 - x1, 1e-6)
        height = max(y2 - y1, 1e-6)
        expanded = (x1 - width * 0.15, y1 - height * 0.08,
                    x2 + width * 0.15, y2 + height * 0.08)
        inside = expanded[0] <= ox <= expanded[2] and expanded[1] <= oy <= expanded[3]

        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        distance = hypot((ox - cx) / width, (oy - cy) / height)
        proximity = max(0.0, 1.0 - distance / 1.5)
        score = (0.75 + 0.25 * proximity) if inside else 0.45 * proximity
        score *= max(0.0, min(1.0, candidate.detection_confidence))

        if score >= threshold and (best is None or score > best.confidence):
            best = Association(candidate.person_id, round(score, 4))

    return best
