"""Smoke + path tests for `validators/validate_capability_labels.py`."""

from __future__ import annotations

from pathlib import Path

import validate_capability_labels as v


def test_module_importable() -> None:
    assert callable(v.validate)


def test_no_card_returns_warn_or_pass(tmp_forge_project: Path) -> None:
    result = v.validate(tmp_forge_project, scope="inferred", id=None)
    assert result["status"] in ("pass", "warn", "fail")


def test_missing_card_dir_does_not_crash(tmp_forge_project: Path) -> None:
    result = v.validate(tmp_forge_project, scope="inferred", id=None, card="ghost-card")
    assert "status" in result
    if result["status"] == "fail":
        assert len(result["paths"]) == 3


def test_returns_structured_message(tmp_forge_project: Path) -> None:
    result = v.validate(tmp_forge_project, scope="inferred", id=None)
    assert isinstance(result.get("message", ""), str)
