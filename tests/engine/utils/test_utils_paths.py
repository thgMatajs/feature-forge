"""Tests for engine.utils.paths helpers."""
from __future__ import annotations

from pathlib import Path

import engine.utils.paths as paths


def test_lifecycle_root_is_single_source(monkeypatch, tmp_path):
    # Patchar lifecycle_root deve fluir pra todos os paths de lifecycle derivados.
    sentinel = tmp_path / "SENTINEL_STATE"
    monkeypatch.setattr(paths, "lifecycle_root", lambda root: sentinel)
    assert paths.memory_l1_path(tmp_path, "feat-x") == sentinel / "feat-x"
