"""Pytest configuration."""

import pytest
import sys
from pathlib import Path

# The project root is already in the path when running pytest from the root,
# so subdirectories can be imported relative to the root.
# No sys.path manipulation is required.
