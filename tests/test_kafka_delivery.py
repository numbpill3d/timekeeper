"""Ensure pipeline producers wait for Kafka delivery acknowledgements."""

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_PRODUCER_SOURCES = (
    _ROOT / "services/ingestion/src/frame_publisher.py",
    _ROOT / "services/vision/src/pipeline.py",
    _ROOT / "services/event-processor/src/main.py",
)


def test_producers_wait_for_delivery_acknowledgement():
    for path in _PRODUCER_SOURCES:
        source = path.read_text(encoding="utf-8")
        assert ".send_and_wait(" in source, path
        assert ".send(" not in source, path
