"""Regression tests for CARD-020 whitespace validation (M-001 from DET-3 code review).

The original implementation in `engine/cards/loader.py:validate_card_yaml`
checked only ASCII space (` ` in coord). Tab/newline characters in a copy-pasted
coordinate would pass shape validation but cause exact-match scanning to fail
silently downstream. These tests assert that ALL whitespace characters are caught.
"""

from pathlib import Path

import pytest

from engine.cards.loader import validate_card_yaml


def _valid_card_skeleton(coordinate: str) -> dict:
    """Minimal valid card manifest with a single gradle-dep signal."""
    return {
        "schema-version": 1,
        "identity": {
            "name": "test-card",
            "version": "1.0.0",
            "category": "backend",
        },
        "detection": {
            "signals": [
                {
                    "type": "gradle-dep",
                    "coordinate": coordinate,
                    "confidence": 0.5,
                }
            ],
            "threshold": 0.5,
        },
    }


def _violations_for(coordinate: str) -> list[str]:
    """Run validator against a card carrying the given coordinate, return CARD-020 hits."""
    manifest = _valid_card_skeleton(coordinate)
    return [v for v in validate_card_yaml(manifest, Path("/tmp/test-card/card.yaml")) if "CARD-020" in v]


def test_card_020_rejects_tab_in_coordinate():
    """Tab character in coordinate must trigger CARD-020 (M-001)."""
    violations = _violations_for("io.ktor:\tktor-client-core")
    assert len(violations) == 1, f"expected exactly 1 CARD-020 violation, got {violations!r}"


def test_card_020_rejects_newline_in_coordinate():
    """Newline character in coordinate must trigger CARD-020 (M-001)."""
    violations = _violations_for("io.ktor:ktor-client-core\n")
    assert len(violations) == 1, f"expected exactly 1 CARD-020 violation, got {violations!r}"


def test_card_020_rejects_ascii_space_in_coordinate():
    """ASCII space must trigger CARD-020 (regression — was already covered)."""
    violations = _violations_for("io.ktor: ktor-client-core")
    assert len(violations) == 1, f"expected exactly 1 CARD-020 violation, got {violations!r}"


def test_card_020_accepts_valid_coordinate():
    """Valid coordinate with no whitespace must NOT trigger CARD-020."""
    violations = _violations_for("io.ktor:ktor-client-core")
    assert violations == [], f"expected no CARD-020 violation for valid coordinate, got {violations!r}"
