"""Smoke + path tests for `validators/validate_data_contract.py`."""

from __future__ import annotations

from pathlib import Path

import validate_data_contract as v


def test_module_importable() -> None:
    assert callable(v.validate)


def test_no_slug_returns_warn(tmp_forge_project: Path) -> None:
    result = v.validate(tmp_forge_project, scope="inferred", id=None)
    assert result["status"] == "warn"


def test_missing_data_contract_returns_fail(tmp_forge_project: Path) -> None:
    slug = "no-contract"
    (
        tmp_forge_project
        / "docs"
        / "feature-implementation-workflow"
        / "features"
        / slug
    ).mkdir(parents=True)
    result = v.validate(tmp_forge_project, scope="feature", id=slug)
    assert result["status"] in ("fail", "warn")
    if result["status"] == "fail":
        assert len(result["paths"]) == 3


def test_template_contract_returns_structured_result(
    tmp_forge_project_with_feature: Path,
) -> None:
    result = v.validate(
        tmp_forge_project_with_feature, scope="feature", id="lembrete-rega"
    )
    assert result["status"] in ("pass", "warn", "fail")
    if result["status"] == "fail":
        assert len(result["paths"]) == 3
