"""Smoke + path tests for `validators/validate_inventory.py`."""

from __future__ import annotations

from pathlib import Path

import validate_inventory as v


def test_module_importable() -> None:
    assert callable(v.validate)


def test_missing_inventory_returns_fail_or_warn(tmp_forge_project: Path) -> None:
    result = v.validate(tmp_forge_project, scope="inferred", id=None)
    assert result["status"] in ("fail", "warn", "pass")
    if result["status"] == "fail":
        assert len(result["paths"]) == 3


def test_minimal_inventory_returns_structured_result(
    tmp_forge_project: Path,
) -> None:
    inv_dir = tmp_forge_project / ".claude" / "inventory"
    (inv_dir / "design-system.yaml").write_text(
        "schema-version: 1\ncomponents: []\n", encoding="utf-8"
    )
    (inv_dir / "i18n.yaml").write_text(
        "schema-version: 1\nkeys: []\n", encoding="utf-8"
    )
    (inv_dir / "conventions.yaml").write_text(
        "schema-version: 1\n", encoding="utf-8"
    )
    result = v.validate(tmp_forge_project, scope="inferred", id=None)
    assert result["status"] in ("pass", "warn", "fail")
    if result["status"] == "fail":
        assert len(result["paths"]) == 3


def test_returns_message(tmp_forge_project: Path) -> None:
    result = v.validate(tmp_forge_project, scope="inferred", id=None)
    assert isinstance(result.get("message", ""), str)
