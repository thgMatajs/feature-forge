"""Smoke + path tests for `validators/validate_readiness.py`."""

from __future__ import annotations

from pathlib import Path

import validate_readiness as v


def test_module_importable() -> None:
    assert callable(v.validate)


def test_no_slug_returns_warn(tmp_forge_project: Path) -> None:
    result = v.validate(tmp_forge_project, scope="inferred", id=None)
    assert result["status"] == "warn"
    assert result.get("what-failed")


def test_missing_review_md_fails_with_three_paths(tmp_forge_project: Path) -> None:
    result = v.validate(tmp_forge_project, scope="feature", id="ghost-slug")
    assert result["status"] == "fail"
    assert len(result["paths"]) == 3


def test_template_review_returns_structured_result(
    tmp_forge_project_with_feature: Path,
) -> None:
    result = v.validate(
        tmp_forge_project_with_feature, scope="feature", id="lembrete-rega"
    )
    assert result["status"] in ("pass", "warn", "fail")
    if result["status"] == "fail":
        assert len(result["paths"]) == 3


def test_review_md_with_ready_verdict_passes(tmp_forge_project: Path) -> None:
    slug = "ready-feature"
    f_root = (
        tmp_forge_project
        / "docs"
        / "feature-implementation-workflow"
        / "features"
        / slug
    )
    f_root.mkdir(parents=True)
    (f_root / "implementation-readiness-review.md").write_text(
        "# Readiness review\n\n"
        "```yaml\n"
        "readiness_verdict:\n"
        "  status: ready\n"
        "  blockers: []\n"
        "  warnings: []\n"
        "```\n",
        encoding="utf-8",
    )
    result = v.validate(tmp_forge_project, scope="feature", id=slug)
    assert result["status"] == "pass"
