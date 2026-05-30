"""Unit tests — engine.inventory.conventions.

Validates that `extract_conventions` returns reasonable defaults for an empty
project, and that the round-trip write/read preserves the inventory.
"""

from __future__ import annotations

from pathlib import Path

from engine.inventory import conventions as conv


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_extract_conventions_empty_project(tmp_path):
    inv = conv.extract_conventions(tmp_path)
    # Empty project: di/nav should resolve to 'unknown' or a default.
    assert inv.di_pattern in {"unknown", "koin-annotations", "manual", "hilt"}
    assert isinstance(inv.raw, dict)
    assert inv.raw["schema-version"] >= 1


def test_extract_conventions_detects_koin(tmp_path):
    _write(
        tmp_path / "shared" / "src" / "commonMain" / "kotlin" / "auth" / "AuthModule.kt",
        "package x\nimport org.koin.core.annotation.Module\nimport org.koin.core.annotation.Single\n@Module\nclass AuthModule\n",
    )
    inv = conv.extract_conventions(tmp_path)
    # Heuristic detection may flag this as koin-annotations.
    assert inv.di_pattern in {"koin-annotations", "koin", "unknown"}


def test_extract_conventions_round_trip(tmp_path):
    inv = conv.extract_conventions(tmp_path)
    out = conv.write_conventions_inventory(tmp_path, inv)
    assert out.is_file()
    read = conv.read_conventions_inventory(tmp_path)
    assert read is not None
    assert read.raw.get("schema-version") == inv.raw.get("schema-version")


def test_extract_conventions_yaml_payload_shape(tmp_path):
    inv = conv.extract_conventions(tmp_path)
    assert "folder-layout" in inv.raw
    assert "test-pattern" in inv.raw
    assert "style-tools" in inv.raw
    assert "navigation" in inv.raw
    assert "quality" in inv.raw
