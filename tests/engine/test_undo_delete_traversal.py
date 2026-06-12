"""H-06 regression: undo delete-feature must refuse paths outside project."""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.undo import _delete_feature_artifacts_guard


def test_delete_guard_rejects_path_outside_project(tmp_path: Path) -> None:
    project_root = tmp_path / "proj"
    project_root.mkdir()
    escaped = tmp_path / "outside"
    escaped.mkdir()

    with pytest.raises(ValueError, match="outside project"):
        _delete_feature_artifacts_guard(project_root, escaped)


def test_delete_guard_accepts_path_inside_project(tmp_path: Path) -> None:
    project_root = tmp_path / "proj"
    project_root.mkdir()
    inside = project_root / "docs" / "feat" / "x"
    inside.mkdir(parents=True)

    # Should not raise.
    _delete_feature_artifacts_guard(project_root, inside)
