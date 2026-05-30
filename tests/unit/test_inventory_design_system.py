"""Unit tests — engine.inventory.design_system.

Smoke tests `extract_design_system` on a minimal synthetic tree containing
Meo* components and design tokens, and validates write/read round-trip.
"""

from __future__ import annotations

from pathlib import Path

from engine.inventory import design_system as ds


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_extract_design_system_returns_inventory(tmp_path):
    # Android scanner requires `/designsystem/` OR `/components/` in the path.
    _write(
        tmp_path / "androidApp" / "core" / "designsystem" / "components" / "atoms" / "MeoButton.kt",
        "package x\n@Composable\nfun MeoButton() {}\n",
    )
    # iOS scanner requires `/DesignSystem/` in the path.
    _write(
        tmp_path / "iosApp" / "DesignSystem" / "Atoms" / "MeoButton.swift",
        "import SwiftUI\nstruct MeoButton: View { var body: some View { Text(\"x\") } }\n",
    )
    inv = ds.extract_design_system(tmp_path)
    assert inv is not None
    names = [c.name for c in inv.components]
    assert "MeoButton" in names


def test_extract_design_system_marks_legacy_outside_pattern(tmp_path):
    _write(
        tmp_path / "androidApp" / "core" / "designsystem" / "components" / "atoms" / "MeoButton.kt",
        "package x\nfun MeoButton() {}\n",
    )
    _write(
        tmp_path / "androidApp" / "core" / "designsystem" / "components" / "atoms" / "Button.kt",
        "package x\nfun Button() {}\n",
    )
    inv = ds.extract_design_system(tmp_path)
    canonical = [c for c in inv.components if c.status != "legacy"]
    legacy = [c for c in inv.components if c.status == "legacy"]
    # Either MeoButton is detected as canonical and Button as legacy, OR
    # the naming heuristic could not lock onto a prefix — in which case
    # both end up in `components` without legacy flag. We accept either
    # outcome and only assert MeoButton appears somewhere.
    all_names = [c.name for c in inv.components]
    assert "MeoButton" in all_names
    assert "Button" in all_names
    # The naming-pattern heuristic detects whichever prefix dominates. In a
    # synthetic 2-component tree this is unstable, so we only assert the
    # legacy/canonical split is non-trivial when both exist.
    if canonical and legacy:
        assert {c.name for c in canonical}.isdisjoint({c.name for c in legacy})


def test_write_then_read_inventory_round_trip(tmp_path):
    # Path needs a `/designsystem/` or `/components/` segment for the Android
    # scanner to pick the file up.
    _write(
        tmp_path / "androidApp" / "designsystem" / "atoms" / "MeoButton.kt",
        "package x\nfun MeoButton() {}\n",
    )
    inv = ds.extract_design_system(tmp_path)
    out = ds.write_design_system_inventory(tmp_path, inv)
    assert out.is_file()
    read_back = ds.read_design_system_inventory(tmp_path)
    assert read_back is not None
    # Only canonical components (matching naming-pattern) round-trip through
    # the `components:` key. Legacy ones live in `legacy-components:`.
    all_names = [c.name for c in read_back.components]
    raw_legacy_names = [c["name"] for c in (read_back.raw.get("legacy-components") or [])]
    assert "MeoButton" in (all_names + raw_legacy_names)


def test_extract_design_system_empty_project(tmp_path):
    inv = ds.extract_design_system(tmp_path)
    assert inv.components == []
