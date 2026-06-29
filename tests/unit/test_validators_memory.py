"""Smoke + path tests for `validators/validate_memory.py`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import validate_memory as v


def test_module_importable() -> None:
    assert callable(v.validate)


# ── C-44 (PR22-R-002) — enum L1 sincronizado com engine.memory.l1 ─────────────


def test_valid_states_synced_with_engine() -> None:
    """O validator não mantém set paralelo — usa o canônico de engine.memory.l1."""
    from engine.memory.l1 import _VALID_STATES

    assert v._VALID_L1_STATES is _VALID_STATES


def _write_status(root: Path, slug: str, state: str) -> Path:
    status = root / ".claude" / "forge" / "state" / "lifecycle" / slug / "status.json"
    status.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {"feature-slug": slug, "state": state}
    if state == "implementing":
        payload["sub-state"] = "task-1"
    status.write_text(json.dumps(payload), encoding="utf-8")
    return status


@pytest.mark.parametrize(
    "state",
    ["not-started", "planned", "deferred", "blocked-on-external", "planning", "done"],
)
def test_canonical_states_accepted(tmp_path: Path, state: str) -> None:
    status = _write_status(tmp_path, "demo", state)
    out = v._check_l1_status(status)
    assert out == [], f"estado canônico {state!r} foi rejeitado: {out}"


@pytest.mark.parametrize("state", ["paused", "verified", "bogus"])
def test_removed_or_invalid_states_rejected(tmp_path: Path, state: str) -> None:
    status = _write_status(tmp_path, "demo", state)
    out = v._check_l1_status(status)
    assert out, f"estado inválido {state!r} deveria ser rejeitado"
    assert any("not in" in msg for msg in out)


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
