"""Regression tests for CARD-021: legacy signal type `dependency` rejected.

Before DET-3 / M-2, cards declaring `type: dependency` were silently ignored
by `engine.init._eval_detection_signals` — leaving "vapor" detection blocks
that looked active but contributed zero confidence. CARD-021 turns that
silent miss into an explicit validation error pointing at the canonical
successor (`gradle-dep`) and the schema doc.

Pattern mirrors `test_card_yaml_validation_whitespace.py` (CARD-020 sibling).
"""

from pathlib import Path

from engine.cards.loader import validate_card_yaml


def _card_021_violations(signals: list[dict]) -> list[str]:
    """Run validator and filter only CARD-021 violations."""
    manifest = {
        "schema-version": 1,
        "identity": {
            "name": "test-card",
            "version": "1.0.0",
            "category": "backend",
        },
        "detection": {
            "signals": signals,
            "threshold": 0.5,
        },
    }
    return [
        v
        for v in validate_card_yaml(manifest, Path("/tmp/test-card/card.yaml"))
        if "CARD-021" in v
    ]


def test_card_with_signal_type_dependency_rejected():
    """`type: dependency` must trigger CARD-021 (M-2 — não-silencioso)."""
    signal = {
        "type": "dependency",
        "file": "gradle/libs.versions.toml",
        "contains": "io.ktor:ktor-client-core",
        "confidence": 0.5,
    }
    violations = _card_021_violations([signal])
    assert len(violations) == 1, (
        f"expected exactly 1 CARD-021 violation, got {violations!r}"
    )


def test_card_021_error_message_points_to_gradle_dep():
    """Mensagem deve guiar o dev pro nome canônico `gradle-dep`."""
    signal = {"type": "dependency", "file": "build.gradle", "contains": "io.ktor"}
    violations = _card_021_violations([signal])
    assert violations, "expected CARD-021 violation, got none"
    assert "gradle-dep" in violations[0], (
        f"CARD-021 message must reference the successor type `gradle-dep`, "
        f"got {violations[0]!r}"
    )


def test_card_with_only_valid_types_passes():
    """Cards usando apenas tipos suportados (`gradle-dep`, `file-content`) não acionam CARD-021."""
    signals = [
        {
            "type": "gradle-dep",
            "coordinate": "io.ktor:ktor-client-core",
            "confidence": 0.5,
        },
        {
            "type": "file-content",
            "glob": "**/build.gradle*",
            "contains": "io.ktor",
            "confidence": 0.3,
        },
    ]
    violations = _card_021_violations(signals)
    assert violations == [], (
        f"expected no CARD-021 violation for valid types, got {violations!r}"
    )
