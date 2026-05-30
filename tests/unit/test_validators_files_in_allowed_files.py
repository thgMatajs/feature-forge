"""Smoke + path tests for `validators/check_files_in_allowed_files.py`."""

from __future__ import annotations

from pathlib import Path

import check_files_in_allowed_files as v


def test_module_importable() -> None:
    assert callable(v.validate)


def test_no_id_returns_pass_or_warn(tmp_forge_project: Path) -> None:
    result = v.validate(tmp_forge_project, scope="inferred", id=None)
    assert result["status"] in ("pass", "warn")


def test_unknown_task_does_not_crash(tmp_forge_project: Path) -> None:
    result = v.validate(tmp_forge_project, scope="task", id="TASK-9999")
    assert "status" in result
    if result["status"] == "fail":
        assert len(result["paths"]) == 3


def test_template_returns_structured_result(
    tmp_forge_project_with_feature: Path,
) -> None:
    result = v.validate(
        tmp_forge_project_with_feature, scope="feature", id="lembrete-rega"
    )
    assert result["status"] in ("pass", "warn", "fail")
