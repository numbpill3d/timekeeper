"""Pytest configuration — adds shared package and service src dirs to sys.path."""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent

# shared pydantic models
sys.path.insert(0, str(ROOT / "shared"))
# individual service src dirs — each named uniquely so no package conflicts
sys.path.insert(0, str(ROOT / "services" / "alert-engine" / "src"))
sys.path.insert(0, str(ROOT / "services" / "event-processor" / "src"))
sys.path.insert(0, str(ROOT / "api" / "src"))
