"""Pytest configuration."""

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRS = (
    ROOT / "shared",
    ROOT / "api" / "src",
    ROOT / "services" / "event-processor" / "src",
    ROOT / "services" / "alert-engine" / "src",
)

for source_dir in SOURCE_DIRS:
    sys.path.insert(0, str(source_dir))
