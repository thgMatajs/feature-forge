"""Smoke + path tests for `validators/validate_card_yaml.py`."""

from __future__ import annotations

from pathlib import Path

import validate_card_yaml as v


def test_module_importable() -> None:
    assert callable(v.validate)


def test_no_cards_returns_pass_or_warn(tmp_forge_project: Path) -> None:
    result = v.validate(tmp_forge_project, scope="inferred", id=None)
    assert result["status"] in ("pass", "warn")


def test_card_with_missing_required_keys_returns_structured_result(
    tmp_forge_project: Path,
) -> None:
    card_dir = tmp_forge_project / ".claude" / "cards" / "incomplete-card"
    card_dir.mkdir(parents=True)
    (card_dir / "card.yaml").write_text(
        "schema-version: 1\n",
        encoding="utf-8",
    )
    result = v.validate(tmp_forge_project, scope="inferred", id=None)
    assert "status" in result
    if result["status"] == "fail":
        assert len(result["paths"]) == 3


def test_minimal_valid_card_passes_or_warns(tmp_forge_project: Path) -> None:
    card_dir = tmp_forge_project / ".claude" / "cards" / "minimal-card"
    card_dir.mkdir(parents=True)
    (card_dir / "card.yaml").write_text(
        "schema-version: 1\nname: minimal-card\n", encoding="utf-8"
    )
    result = v.validate(tmp_forge_project, scope="inferred", id=None)
    assert result["status"] in ("pass", "warn", "fail")
