"""Keep the default vision image self-contained for offline startup."""

from pathlib import Path


def test_vision_dockerfile_bundles_verified_osnet_weights():
    dockerfile = (Path(__file__).parents[1] / "services" / "vision" / "Dockerfile").read_text()

    assert "osnet_x1_0_imagenet.pth" in dockerfile
    assert "fe2d63f9157c28a4a8d8ca29bec12d5b2988ac0346d712025789ea9174968e79" in dockerfile
    assert "sha256sum -c -" in dockerfile
