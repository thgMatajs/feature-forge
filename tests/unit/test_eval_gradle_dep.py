"""Tests for gradle-dep signal type evaluation.

Cobre AC-1..AC-6 do SPEC det-3-gradle-dep-signal.md + edge cases
(TOML mal-formado, coordenada inválida, ambos formatos co-existindo).

CARD-020 tests cobrem validação de shape no loader (note: SPEC §AC-8
diz "CARD-019 ou next free"; CARD-019 já é usado por legacy-marker,
então a regra nova alocada é CARD-020 — ver `.planning/det-3/deviations.md`).
"""

from pathlib import Path

import pytest

from engine.init import _eval_detection_signals, _eval_gradle_dep

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _detection(coordinate: str, confidence: float = 0.5) -> dict:
    return {"signals": [{"type": "gradle-dep", "coordinate": coordinate, "confidence": confidence}]}


def test_ac1_toml_only_module_format() -> None:
    """AC-1: libs.versions.toml com `module = "io.ktor:..."` → match."""
    score, matched = _eval_detection_signals(
        FIXTURES / "gradle-dep-toml-only",
        _detection("io.ktor:ktor-client-core"),
    )
    assert score == 0.5
    assert any("io.ktor:ktor-client-core" in m for m in matched)


def test_ac2_toml_split_group_name_format() -> None:
    """AC-2: libs.versions.toml com `group + name` separados → match."""
    score, _ = _eval_detection_signals(
        FIXTURES / "gradle-dep-toml-split",
        _detection("io.ktor:ktor-client-core"),
    )
    assert score == 0.5


def test_ac3_build_gradle_legacy() -> None:
    """AC-3: build.gradle.kts declarando dep diretamente → match."""
    score, _ = _eval_detection_signals(
        FIXTURES / "gradle-dep-legacy",
        _detection("io.ktor:ktor-client-core"),
    )
    assert score == 0.5


def test_ac4_hybrid_no_double_counting() -> None:
    """AC-4: catálogo + build.gradle → match exatamente uma vez."""
    score, _ = _eval_detection_signals(
        FIXTURES / "gradle-dep-hybrid",
        _detection("io.ktor:ktor-client-core"),
    )
    assert score == 0.5  # confidence única, sem soma duplicada


def test_ac5_negative_no_match() -> None:
    """AC-5: TOML sem a coordenada → sem match."""
    score, _ = _eval_detection_signals(
        FIXTURES / "gradle-dep-negative",
        _detection("io.ktor:ktor-client-core"),
    )
    assert score == 0.0


def test_ac6_file_content_preserved() -> None:
    """AC-6: file-content em **/*.kt continua funcionando após introdução de gradle-dep."""
    score, _ = _eval_detection_signals(
        FIXTURES / "gradle-dep-file-content-preserved",
        {"signals": [{"type": "file-content", "glob": "**/*.kt", "contains": "io.ktor.client", "confidence": 0.2}]},
    )
    assert score == 0.2


def test_helper_returns_false_for_missing_coordinate() -> None:
    """Defesa: coordenada ausente retorna False (não raise)."""
    assert _eval_gradle_dep(FIXTURES / "gradle-dep-negative", "io.ktor:ktor-client-core") is False


def test_helper_handles_empty_coordinate() -> None:
    """Defesa: coordenada vazia/None retorna False (não raise)."""
    assert _eval_gradle_dep(FIXTURES / "gradle-dep-toml-only", "") is False
    assert _eval_gradle_dep(FIXTURES / "gradle-dep-toml-only", None) is False  # type: ignore[arg-type]


def test_helper_handles_malformed_toml(tmp_path: Path) -> None:
    """Defesa: TOML mal-formado não bloqueia (try/except silencioso)."""
    (tmp_path / "gradle").mkdir()
    (tmp_path / "gradle" / "libs.versions.toml").write_text("not valid toml [[[", encoding="utf-8")
    assert _eval_gradle_dep(tmp_path, "io.ktor:ktor-client-core") is False


# ── CARD-020 (shape validation for gradle-dep coordinate) ────────────────────
# Note: SPEC §AC-8 allowed "CARD-019 or next free". CARD-019 is already
# legacy-marker, so this rule lands as CARD-020. See `.planning/det-3/deviations.md`.


def _minimal_card(detection_signals: list[dict]) -> dict:
    """Build minimal valid card.yaml dict with custom detection.signals."""
    return {
        "schema-version": 1,
        "identity": {
            "name": "test-card",
            "version": "1.0.0",
            "category": "stack",
            "maturity": "canonical",
        },
        "provides": ["test-capability"],
        "detection": {"signals": detection_signals},
    }


def test_card020_coordinate_shape_valid(tmp_path: Path) -> None:
    """CARD-020: coordinate válida no shape `<group>:<artifact>`."""
    from engine.cards.loader import validate_card_yaml

    (tmp_path / "README.md").write_text("# test", encoding="utf-8")
    valid = _minimal_card([
        {"type": "gradle-dep", "coordinate": "io.ktor:ktor-client-core", "confidence": 0.5}
    ])
    violations = validate_card_yaml(valid, tmp_path)
    assert not any("CARD-020" in v for v in violations), violations


def test_card020_coordinate_rejects_version_suffix(tmp_path: Path) -> None:
    """CARD-020: rejeita coordenada com versão sufixada."""
    from engine.cards.loader import validate_card_yaml

    (tmp_path / "README.md").write_text("# test", encoding="utf-8")
    bad = _minimal_card([
        {"type": "gradle-dep", "coordinate": "io.ktor:ktor-client-core:2.3.7", "confidence": 0.5}
    ])
    violations = validate_card_yaml(bad, tmp_path)
    assert any("CARD-020" in v for v in violations), violations


def test_card020_coordinate_rejects_missing_colon(tmp_path: Path) -> None:
    """CARD-020: rejeita coordenada sem ':' separator."""
    from engine.cards.loader import validate_card_yaml

    (tmp_path / "README.md").write_text("# test", encoding="utf-8")
    bad = _minimal_card([
        {"type": "gradle-dep", "coordinate": "io.ktor", "confidence": 0.5}
    ])
    violations = validate_card_yaml(bad, tmp_path)
    assert any("CARD-020" in v for v in violations), violations
