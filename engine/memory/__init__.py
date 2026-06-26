"""Memory subsystem — L1 (per-feature WIP) + L2 (project) + L3 (read-only proxy to auto-memory).

Public surface:
- engine.memory.l1        — per-feature WIP (.claude/forge/state/lifecycle/{slug}/)
- engine.memory.l2        — project-wide patterns (.claude/memory/L2-project.yaml)
- engine.memory.l3        — read-only proxy over Claude Code auto-memory (~/.claude/...)
- engine.memory.distiller — proposal queue + fingerprinting for forge evolve

All modules share a common error type so callers can `except MemoryError` once.
"""

from __future__ import annotations


class MemoryError(Exception):
    """Raised on any memory subsystem failure (parse, write, lock, schema)."""
