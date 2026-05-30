"""Smoke + path tests for `validators/validate_memory.py`."""

from __future__ import annotations

from pathlib import Path

import validate_memory as v


def test_module_importable() -> None:
    assert callable(v.validate)


def test_empty_memory_returns_pass_or_warn(tmp_forge_project: Path) -> None:
    result = v.validate(tmp_forge_project, scope="inferred", id=None)
    assert result["status"] in ("pass", "warn", "fail")
    if result["status"] == "fail":
        assert len(result["paths"]) == 3


def test_minimal_l2_yaml_returns_structured_result(tmp_forge_project: Path) -> None:
    l2 = tmp_forge_project / ".claude" / "memory" / "L2-project.yaml"
    l2.write_text(
        "schema-version: 1\nproject-slug: test\nfacts: []\n", encoding="utf-8"
    )
    result = v.validate(tmp_forge_project, scope="inferred", id=None)
    assert result["status"] in ("pass", "warn", "fail")


def test_l2_yaml_with_missing_fields_does_not_crash(
    tmp_forge_project: Path,
) -> None:
    l2 = tmp_forge_project / ".claude" / "memory" / "L2-project.yaml"
    l2.write_text("schema-version: 1\n", encoding="utf-8")
    result = v.validate(tmp_forge_project, scope="inferred", id=None)
    assert "status" in result
    if result["status"] == "fail":
        assert len(result["paths"]) == 3
