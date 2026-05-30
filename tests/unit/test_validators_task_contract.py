"""Smoke + path tests for `validators/validate_task_contract.py`."""

from __future__ import annotations

from pathlib import Path

import validate_task_contract as v


def test_module_importable() -> None:
    assert callable(v.validate)


def test_no_slug_no_task_returns_warn_or_fail(tmp_forge_project: Path) -> None:
    result = v.validate(tmp_forge_project, scope="inferred", id=None)
    assert result["status"] in ("warn", "fail")


def test_unknown_task_id_returns_fail(tmp_forge_project: Path) -> None:
    result = v.validate(tmp_forge_project, scope="task", id="TASK-9999")
    assert result["status"] == "fail"
    assert len(result["paths"]) == 3


def test_empty_tasks_dir_in_feature_returns_fail(tmp_forge_project: Path) -> None:
    slug = "empty-tasks"
    (
        tmp_forge_project
        / "docs"
        / "feature-implementation-workflow"
        / "features"
        / slug
        / "tasks"
    ).mkdir(parents=True)
    result = v.validate(tmp_forge_project, scope="feature", id=slug)
    assert result["status"] == "fail"
    assert len(result["paths"]) == 3


def test_template_task_yaml_returns_structured_result(
    tmp_forge_project_with_feature: Path,
) -> None:
    tasks_dir = (
        tmp_forge_project_with_feature
        / "docs"
        / "feature-implementation-workflow"
        / "features"
        / "lembrete-rega"
        / "tasks"
    )
    (tasks_dir / "TASK-0001.yaml").write_text(
        "task_id: TASK-0001\n"
        "title: stub\n"
        "evidence_required: []\n"
        "depends_on: []\n",
        encoding="utf-8",
    )
    result = v.validate(
        tmp_forge_project_with_feature, scope="task", id="TASK-0001"
    )
    assert result["status"] in ("pass", "warn", "fail")
    if result["status"] == "fail":
        assert len(result["paths"]) == 3
