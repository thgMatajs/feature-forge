"""Tests for engine.detection.composer (W5.1 — DET-6).

Cobertura: AC-5 (composer correctly identifies card per (axis, platform)).
Skeleton: 3 ciclos TDD — single card → Cell, two cards → Conflict, zero → None.
Hardening (W5 review r1): boundary, ordering determinístico, range validation.

Reuso: tests usam `_eval_detection_signals` real via tmp_path fixtures
(build.gradle.kts), evitando mocks. Bug `_SKIP_DIRS` em paths sob
`.claude/worktrees/` justifica tmp_path em vez de tests/fixtures/.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.detection.composer import (
    Cell,
    Conflict,
    compose_backend_axes,
)


def _make_ktor_card() -> dict:
    """Card spec mock pra ktor-client (axis=data, android+kmp).

    Ktor é o KMP HTTP client canônico do projeto — platforms cobre
    `["android", "kmp"]` pra alinhar com o domínio real e com o
    integration test W5.2.
    """
    return {
        "card_id": "ktor-client",
        "axis": "data",
        "platforms": ["android", "kmp"],
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

    # Defesa secundária (LOW-002): _make_ktor_card declara android+kmp, então
    # (data, kmp) também deve ser Cell singular do mesmo card. Garante que
    # composer respeita a lista de platforms per-card.
    kmp_cell = result["data"]["kmp"]
    assert isinstance(kmp_cell, Cell), (
        f"expected Cell at (data, kmp), got {type(kmp_cell).__name__}: {kmp_cell!r}"
    )
    assert kmp_cell.card_id == "ktor-client"


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


# ── HIGH-001 — boundary score == threshold qualifica (>=, não >) ─────────────


def test_composer_includes_card_when_score_equals_threshold(
    tmp_path: Path,
) -> None:
    """Boundary: score exatamente igual ao threshold conta como match.

    Pina a semântica `score >= threshold` (inequality não-estrita) — protege
    contra refator silencioso de `<` pra `<=` no `continue` que faria cards
    reais sumirem do composer.

    Setup: signal único com confidence=0.3 que casa, score esperado = 0.3,
    threshold per-card = 0.3 (igual). Resultado deve ser Cell, não None.
    """
    _write_gradle_with_ktor(tmp_path)

    boundary_card = {
        "card_id": "boundary-card",
        "axis": "data",
        "platforms": ["android"],
        "detection": {
            "threshold": 0.3,
            "signals": [
                {
                    "type": "file-content",
                    "glob": "**/build.gradle*",
                    "contains": "io.ktor:ktor-client-",
                    "confidence": 0.3,
                }
            ],
        },
    }

    result = compose_backend_axes(tmp_path, [boundary_card])

    cell = result["data"]["android"]
    assert isinstance(cell, Cell), (
        f"score == threshold (0.3 == 0.3) must qualify; got "
        f"{type(cell).__name__}: {cell!r}"
    )
    assert cell.card_id == "boundary-card"
    assert cell.score == pytest.approx(0.3)


# ── HIGH-002 — Conflict.candidates ordenado por card_id ──────────────────────


def test_composer_conflict_candidates_ordered_by_card_id(
    tmp_path: Path,
) -> None:
    """Conflict.candidates vem ordenado alfabeticamente por card_id.

    Determinístico independente da ordem de `active_cards` no input —
    consumers downstream (W7) podem confiar em ordem estável entre runs.

    Estratégia: passa cards em ordem REVERSA da alfabética (`retrofit`
    antes de `ktor`) e confirma que o tuple resultante está ordenado
    alfabético (`ktor` antes de `retrofit`).
    """
    _write_gradle_with_both(tmp_path)

    # Ordem REVERSA da alfabética: retrofit (r) vem antes de ktor (k).
    active_cards = [_make_retrofit_card(), _make_ktor_card()]
    result = compose_backend_axes(tmp_path, active_cards)

    cell = result["data"]["android"]
    assert isinstance(cell, Conflict), (
        f"expected Conflict, got {type(cell).__name__}: {cell!r}"
    )

    candidate_ids = [c.card_id for c in cell.candidates]
    assert candidate_ids == sorted(candidate_ids), (
        f"Conflict.candidates must be sorted by card_id; got {candidate_ids!r}"
    )
    assert candidate_ids == ["ktor-client", "retrofit-client"], (
        f"expected ['ktor-client', 'retrofit-client'], got {candidate_ids!r}"
    )


# ── MED-001 — threshold fora de [0.0, 1.0] raise ValueError ──────────────────


def test_composer_raises_on_invalid_threshold(tmp_path: Path) -> None:
    """Card com `detection.threshold` fora de `[0.0, 1.0]` levanta ValueError.

    Defensividade contra card.yaml mal-formado — falhar alto é melhor que
    mascarar bug (threshold < 0 silencia gating; threshold > 1 exclui todo
    card).
    """
    _write_gradle_with_ktor(tmp_path)

    bad_low_card = {
        "card_id": "bad-low",
        "axis": "data",
        "platforms": ["android"],
        "detection": {
            "threshold": -0.1,
            "signals": [
                {
                    "type": "file-content",
                    "glob": "**/build.gradle*",
                    "contains": "io.ktor:ktor-client-",
                    "confidence": 0.6,
                }
            ],
        },
    }

    with pytest.raises(ValueError, match=r"threshold.*outside \[0\.0, 1\.0\]"):
        compose_backend_axes(tmp_path, [bad_low_card])

    bad_high_card = {
        "card_id": "bad-high",
        "axis": "data",
        "platforms": ["android"],
        "detection": {
            "threshold": 1.5,
            "signals": [
                {
                    "type": "file-content",
                    "glob": "**/build.gradle*",
                    "contains": "io.ktor:ktor-client-",
                    "confidence": 0.6,
                }
            ],
        },
    }

    with pytest.raises(ValueError, match=r"threshold.*outside \[0\.0, 1\.0\]"):
        compose_backend_axes(tmp_path, [bad_high_card])
