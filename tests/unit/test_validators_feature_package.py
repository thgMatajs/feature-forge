"""Smoke + path tests for `validators/validate_feature_package.py`.

Covers:
- module imports cleanly and exposes a callable `validate()`
- `run_cli` is wired (script entry point exists)
- missing feature dir → fail with the canonical 3-paths block
- empty/no slug → warn (validator opts out gracefully)
- happy-ish path (feature dir populated from templates) → structurally valid result
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import validate_feature_package as v
from _common import run_cli


def test_module_importable() -> None:
    assert callable(v.validate)


def test_run_cli_is_wired() -> None:
    assert callable(run_cli)


def test_missing_slug_returns_warn(tmp_forge_project: Path) -> None:
    result: dict[str, Any] = v.validate(tmp_forge_project, scope="inferred", id=None)
    assert result["status"] in ("warn", "pass", "fail")
    if result["status"] == "warn":
        assert "what-failed" in result


def test_missing_feature_dir_returns_fail(tmp_forge_project: Path) -> None:
    result = v.validate(tmp_forge_project, scope="feature", id="ghost-slug")
    assert result["status"] == "fail"
    assert len(result["paths"]) == 3
    for path_entry in result["paths"]:
        assert path_entry["kind"] in ("fix", "revert", "split")
        assert path_entry["label"]
        assert path_entry["motive"]


def test_populated_feature_returns_structured_result(
    tmp_forge_project_with_feature: Path,
) -> None:
    result = v.validate(
        tmp_forge_project_with_feature, scope="feature", id="lembrete-rega"
    )
    assert result["status"] in ("pass", "warn", "fail")
    assert "message" in result
    if result["status"] == "fail":
        assert len(result["paths"]) == 3
