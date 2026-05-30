"""Smoke + path tests for `validators/check_no_invented_behavior.py`."""

from __future__ import annotations

from pathlib import Path

import check_no_invented_behavior as v


def test_module_importable() -> None:
    assert callable(v.validate)


def test_no_slug_returns_pass_or_warn(tmp_forge_project: Path) -> None:
    result = v.validate(tmp_forge_project, scope="inferred", id=None)
    assert result["status"] in ("pass", "warn")


def test_missing_feature_does_not_crash(tmp_forge_project: Path) -> None:
    result = v.validate(tmp_forge_project, scope="feature", id="ghost")
    assert result["status"] in ("pass", "warn", "fail")
    if result["status"] == "fail":
        assert len(result["paths"]) == 3


def test_template_returns_structured_result(
    tmp_forge_project_with_feature: Path,
) -> None:
    result = v.validate(
        tmp_forge_project_with_feature, scope="feature", id="lembrete-rega"
    )
    assert "status" in result
    assert "message" in result
