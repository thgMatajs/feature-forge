"""Utility helpers used across all engine modules.

Anything in this package must be:
- stdlib-first (PyYAML is the only external dep)
- side-effect free at import time
- usable by every command (no upward dependencies on init/plan/etc.)
"""
