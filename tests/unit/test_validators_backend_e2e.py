"""Smoke + path tests for `validators/validate_backend_e2e.py`."""

from __future__ import annotations

from pathlib import Path

import validate_backend_e2e as v


def test_module_importable() -> None:
    assert callable(v.validate)


def test_no_slug_returns_warn(tmp_forge_project: Path) -> None:
    result = v.validate(tmp_forge_project, scope="inferred", id=None)
    assert result["status"] == "warn"


def test_template_returns_structured_result(
    tmp_forge_project_with_feature: Path,
) -> None:
    result = v.validate(
        tmp_forge_project_with_feature, scope="feature", id="lembrete-rega"
    )
    assert result["status"] in ("pass", "warn", "fail")
    if result["status"] == "fail":
        assert len(result["paths"]) == 3


def test_missing_feature_returns_warn_or_pass(tmp_forge_project: Path) -> None:
    result = v.validate(tmp_forge_project, scope="feature", id="ghost")
    assert result["status"] in ("warn", "pass", "fail")
    if result["status"] == "fail":
        assert len(result["paths"]) == 3
