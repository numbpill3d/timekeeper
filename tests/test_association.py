"""Tests for explainable frame-level person/object attribution."""

from uuid import uuid4

from association import PersonCandidate, associate_person


def test_object_inside_person_box_is_associated():
    person_id = uuid4()
    result = associate_person(
        (0.42, 0.58, 0.50, 0.68),
        [PersonCandidate(person_id, (0.25, 0.10, 0.70, 0.90), 0.95)],
    )
    assert result is not None
    assert result.person_id == person_id
    assert result.method == "person_object_proximity"
    assert result.confidence > 0.55


def test_distant_object_is_not_associated():
    result = associate_person(
        (0.80, 0.80, 0.95, 0.95),
        [PersonCandidate(uuid4(), (0.05, 0.05, 0.25, 0.50), 0.99)],
    )
    assert result is None


def test_low_confidence_person_is_not_promoted_to_identity():
    result = associate_person(
        (0.42, 0.58, 0.50, 0.68),
        [PersonCandidate(uuid4(), (0.25, 0.10, 0.70, 0.90), 0.40)],
    )
    assert result is None


def test_ambiguous_overlapping_people_are_not_promoted_to_identity():
    object_bbox = (0.46, 0.56, 0.54, 0.64)
    candidates = [
        PersonCandidate(uuid4(), (0.10, 0.10, 0.90, 0.90), 0.95),
        PersonCandidate(uuid4(), (0.10, 0.10, 0.90, 0.90), 0.94),
    ]

    assert associate_person(object_bbox, candidates) is None
