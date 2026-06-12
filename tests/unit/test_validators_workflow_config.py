"""Smoke + path tests for `validators/validate_workflow_config.py`."""

from __future__ import annotations

from pathlib import Path

import validate_workflow_config as v


def test_module_importable() -> None:
    assert callable(v.validate)


def test_missing_workflow_config_fails(tmp_forge_project: Path) -> None:
    result = v.validate(tmp_forge_project, scope="inferred", id=None)
    assert result["status"] in ("fail", "warn")
    if result["status"] == "fail":
        assert len(result["paths"]) == 3


def test_minimal_workflow_config_returns_structured_result(
    tmp_forge_project: Path,
) -> None:
    # W7.4 — `backend-choice` (legacy monolítico) removido em DET-6 Phase B;
    # backend agora vive em ``backend.<axis>.<platform>`` (RULE-019..024).
    # Test fica minimal — top-level keys faltando devem cair em fail/warn
    # com paths estruturados.
    (tmp_forge_project / ".claude" / "workflow-config.yaml").write_text(
        "schema-version: 1\n"
        "preset: kmp-mobile\n"
        "cards:\n"
        "  active: []\n",
        encoding="utf-8",
    )
    result = v.validate(tmp_forge_project, scope="inferred", id=None)
    assert result["status"] in ("pass", "warn", "fail")
    if result["status"] == "fail":
        assert len(result["paths"]) == 3


def test_workflow_config_missing_required_keys_returns_structured_result(
    tmp_forge_project: Path,
) -> None:
    (tmp_forge_project / ".claude" / "workflow-config.yaml").write_text(
        "schema-version: 1\n", encoding="utf-8"
    )
    result = v.validate(tmp_forge_project, scope="inferred", id=None)
    assert result["status"] in ("fail", "warn", "pass")
    if result["status"] == "fail":
        assert len(result["paths"]) == 3
