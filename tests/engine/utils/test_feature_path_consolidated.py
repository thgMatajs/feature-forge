"""M-04 regression: feature_path resolves non-product subtypes correctly."""

from __future__ import annotations

from pathlib import Path

from engine.utils.paths import feature_path


def test_feature_path_product_default_layout(tmp_path: Path) -> None:
    result = feature_path(tmp_path, "auth-login", subtype="product")
    expected = tmp_path / "docs" / "feature-implementation-workflow" / "features" / "auth-login"
    assert result == expected


def test_feature_path_non_product_subtype(tmp_path: Path) -> None:
    result = feature_path(tmp_path, "rename-helpers", subtype="refactor")
    assert "non-product" in str(result)
    assert result.name == "rename-helpers"
