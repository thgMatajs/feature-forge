"""Tests for engine.detection.composer (W5.1 — DET-6).

Cobertura: AC-5 (composer correctly identifies card per (axis, platform)).
Skeleton: 3 ciclos TDD — single card → Cell, two cards → Conflict, zero → None.

Reuso: tests usam `_eval_detection_signals` real via tmp_path fixtures
(build.gradle.kts), evitando mocks. Bug `_SKIP_DIRS` em paths sob
`.claude/worktrees/` justifica tmp_path em vez de tests/fixtures/.
"""

from __future__ import annotations

from pathlib import Path

from engine.detection.composer import (
    Cell,
    Conflict,
    compose_backend_axes,
)


def _make_ktor_card() -> dict:
    """Card spec mock pra ktor-client (axis=data, android+kmp)."""
    return {
        "card_id": "ktor-client",
        "axis": "data",
        "platforms": ["android"],
        "detection": {
            "signals": [
                {
                    "type": "file-content",
                    "glob": "**/build.gradle*",
                    "contains": "io.ktor:ktor-client-",
                    "confidence": 0.6,
                }
            ]
        },
    }


def _make_retrofit_card() -> dict:
    """Card spec mock pra retrofit-client (axis=data, android)."""
    return {
        "card_id": "retrofit-client",
        "axis": "data",
        "platforms": ["android"],
        "detection": {
            "signals": [
                {
                    "type": "file-content",
                    "glob": "**/build.gradle*",
                    "contains": "com.squareup.retrofit2:retrofit",
                    "confidence": 0.7,
                }
            ]
        },
    }


def _write_gradle_with_ktor(root: Path) -> None:
    gradle = root / "build.gradle.kts"
    gradle.write_text(
        'dependencies {\n'
        '    implementation("io.ktor:ktor-client-core:2.3.0")\n'
        '}\n',
        encoding="utf-8",
    )


def _write_gradle_with_retrofit(root: Path) -> None:
    gradle = root / "build.gradle.kts"
    gradle.write_text(
        'dependencies {\n'
        '    implementation("com.squareup.retrofit2:retrofit:2.9.0")\n'
        '}\n',
        encoding="utf-8",
    )


def _write_gradle_with_both(root: Path) -> None:
    gradle = root / "build.gradle.kts"
    gradle.write_text(
        'dependencies {\n'
        '    implementation("io.ktor:ktor-client-core:2.3.0")\n'
        '    implementation("com.squareup.retrofit2:retrofit:2.9.0")\n'
        '}\n',
        encoding="utf-8",
    )


# ── Ciclo 1 — single card above threshold emits Cell ─────────────────────────


def test_composer_emits_active_cell_when_single_card_above_threshold(
    tmp_path: Path,
) -> None:
    """Quando 1 card bate signals acima do threshold, cell = Cell(card, score, matched)."""
    _write_gradle_with_ktor(tmp_path)

    active_cards = [_make_ktor_card()]
    result = compose_backend_axes(tmp_path, active_cards)

    assert "data" in result, f"axis 'data' missing from result: {result!r}"
    assert "android" in result["data"], f"platform 'android' missing: {result['data']!r}"

    cell = result["data"]["android"]
    assert isinstance(cell, Cell), f"expected Cell, got {type(cell).__name__}: {cell!r}"
    assert cell.card_id == "ktor-client"
    assert cell.score >= 0.3
    assert len(cell.matched_signals) >= 1


# ── Ciclo 2 — two cards above threshold emit Conflict ────────────────────────


def test_composer_emits_conflict_when_two_cards_above_threshold(
    tmp_path: Path,
) -> None:
    """Quando 2 cards batem signals acima do threshold pra mesma cell, Conflict."""
    _write_gradle_with_both(tmp_path)

    active_cards = [_make_ktor_card(), _make_retrofit_card()]
    result = compose_backend_axes(tmp_path, active_cards)

    cell = result["data"]["android"]
    assert isinstance(cell, Conflict), (
        f"expected Conflict, got {type(cell).__name__}: {cell!r}"
    )
    assert len(cell.candidates) == 2
    candidate_ids = {c.card_id for c in cell.candidates}
    assert candidate_ids == {"ktor-client", "retrofit-client"}


# ── Ciclo 3 — no match emits None ────────────────────────────────────────────


def test_composer_emits_null_when_no_match(tmp_path: Path) -> None:
    """Quando nenhum card bate signals acima do threshold, cell é None."""
    # tmp_path vazio — sem build.gradle, signals não casam.

    active_cards = [_make_ktor_card()]
    result = compose_backend_axes(tmp_path, active_cards)

    assert result["data"]["android"] is None
