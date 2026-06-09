"""Tests for CardManifest.env_needs / sensitive_env_needs parsing (QA-11 wave 2)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from engine.cards.loader import load_card


def _write_card(card_dir: Path, qa_extensions: dict | None = None) -> None:
    """Helper: escreve card.yaml mínimo válido + README.md."""
    data = {
        "schema-version": 1,
        "identity": {
            "name": "test-card",
            "version": "1.0.0",
            "description": "fixture card pra QA-11 tests",
            "category": "kmp",
            "maturity": "stable",
        },
        "provides": ["kotlin-multiplatform"],
    }
    if qa_extensions is not None:
        data["qa-extensions"] = qa_extensions

    card_dir.mkdir(parents=True, exist_ok=True)
    (card_dir / "card.yaml").write_text(
        yaml.safe_dump(data, sort_keys=False), encoding="utf-8"
    )
    (card_dir / "README.md").write_text("# test-card\n", encoding="utf-8")


def test_load_card_parses_env_needs_into_tuple(tmp_path):
    """env-needs YAML vira tupla imutável no CardManifest."""
    card_dir = tmp_path / "test-card"
    _write_card(card_dir, qa_extensions={"env-needs": ["JAVA_HOME", "MY_VAR"]})

    manifest = load_card(card_dir)

    assert manifest.env_needs == ("JAVA_HOME", "MY_VAR")
    assert isinstance(manifest.env_needs, tuple)


def test_load_card_classifies_sensitive_env_needs(tmp_path):
    """Vars que batem SENSITIVE_PATTERN são separadas em sensitive_env_needs."""
    card_dir = tmp_path / "test-card"
    _write_card(
        card_dir,
        qa_extensions={"env-needs": ["JAVA_HOME", "GITHUB_TOKEN", "DB_PASSWORD"]},
    )

    manifest = load_card(card_dir)

    assert manifest.env_needs == ("JAVA_HOME", "GITHUB_TOKEN", "DB_PASSWORD")
    assert manifest.sensitive_env_needs == ("GITHUB_TOKEN", "DB_PASSWORD")


def test_load_card_no_env_needs_defaults_empty(tmp_path):
    """Card sem qa-extensions.env-needs tem tuplas vazias por default."""
    card_dir = tmp_path / "test-card"
    _write_card(card_dir, qa_extensions=None)

    manifest = load_card(card_dir)

    assert manifest.env_needs == ()
    assert manifest.sensitive_env_needs == ()
