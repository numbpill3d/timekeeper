"""Pytest configuration."""

import os

# Keep auth-dependent modules independent of pytest's file collection order.
# Production startup still requires an explicitly configured JWT_SECRET.
os.environ.setdefault("JWT_SECRET", "unit-test-secret-012345678901234567890123")

# The project root is already in the path when running pytest from the root,
# so subdirectories can be imported relative to the root. No sys.path
# manipulation is required.
