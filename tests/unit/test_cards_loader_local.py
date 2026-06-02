"""Unit tests — loader cascade canon ∪ local overlay.

Cobre:
  - happy union (canon + local lidos juntos)
  - conflito canon×local (CardConflictError hard fail)
  - dir local inexistente (silent canon-only)
  - dir local vazio (warning skip — não levanta)
  - card.yaml local malformado (ValidationError com path)
  - origin tag (canon=canon, local=local)
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from engine.cards import CardError, CardConflictError, loader


def _valid_card_dict(name: str = "demo-card", provides: list[str] | None = None) -> dict:
    return {
        "schema-version": 1,
        "identity": {
            "name": name,
            "version": "1.0.0",
            "description": "Demo card",
            "category": "kmp",
            "maturity": "stable",
        },
        "provides": provides or ["kotlin-multiplatform"],
        "requires": [],
        "conflicts-with": [],
    }


def _write_card_dir(card_dir: Path, data: dict) -> None:
    card_dir.mkdir(parents=True, exist_ok=True)
    (card_dir / "card.yaml").write_text(
        yaml.safe_dump(data, sort_keys=False), encoding="utf-8"
    )
    (card_dir / "README.md").write_text("# test\n", encoding="utf-8")


def _make_project(tmp_path: Path) -> Path:
    """Build a fake project root with `.claude/cards/` ready for cascade."""
    project = tmp_path / "fake-project"
    (project / ".claude" / "cards").mkdir(parents=True)
    return project


# ── Happy union ─────────────────────────────────────────────────────────────


def test_cascade_returns_canon_only_when_local_absent(tmp_path):
    project = _make_project(tmp_path)
    _write_card_dir(project / ".claude" / "cards" / "canon-a", _valid_card_dict("canon-a"))
    manifests = loader.load_all_cards(project)
    assert [m.name for m in manifests] == ["canon-a"]
    assert manifests[0].origin == "canon"


def test_cascade_unions_canon_and_local(tmp_path):
    project = _make_project(tmp_path)
    _write_card_dir(project / ".claude" / "cards" / "canon-a", _valid_card_dict("canon-a"))
    _write_card_dir(
        project / ".claude" / "cards" / "local" / "team-b",
        _valid_card_dict("team-b", provides=["kotlin-multiplatform"]),
    )
    manifests = loader.load_all_cards(project)
    names_and_origins = {(m.name, m.origin) for m in manifests}
    assert ("canon-a", "canon") in names_and_origins
    assert ("team-b", "local") in names_and_origins


# ── Conflict ────────────────────────────────────────────────────────────────


def test_cascade_hard_fails_on_canon_local_name_collision(tmp_path):
    project = _make_project(tmp_path)
    _write_card_dir(project / ".claude" / "cards" / "collide", _valid_card_dict("collide"))
    _write_card_dir(
        project / ".claude" / "cards" / "local" / "collide",
        _valid_card_dict("collide"),
    )
    with pytest.raises(CardConflictError) as exc:
        loader.load_all_cards(project)
    assert "colisão canon×local" in str(exc.value)
    assert "collide" in str(exc.value)


# ── Edge cases ──────────────────────────────────────────────────────────────


def test_cascade_silent_when_local_root_missing(tmp_path):
    """`.claude/cards/local/` ausente é canon-only, sem warning."""
    project = _make_project(tmp_path)
    _write_card_dir(project / ".claude" / "cards" / "canon-only", _valid_card_dict("canon-only"))
    # nota: local/ NÃO é criado
    manifests = loader.load_all_cards(project)
    assert [m.name for m in manifests] == ["canon-only"]


def test_cascade_skips_empty_local_dir(tmp_path):
    """Dir `local/<name>/` existe sem card.yaml → skip silencioso."""
    project = _make_project(tmp_path)
    _write_card_dir(project / ".claude" / "cards" / "canon-a", _valid_card_dict("canon-a"))
    empty_local = project / ".claude" / "cards" / "local" / "no-card"
    empty_local.mkdir(parents=True)
    # nenhum card.yaml dentro
    manifests = loader.load_all_cards(project)
    assert [m.name for m in manifests] == ["canon-a"]


def test_cascade_raises_on_malformed_local_card_yaml(tmp_path):
    project = _make_project(tmp_path)
    bad_dir = project / ".claude" / "cards" / "local" / "bad"
    bad_dir.mkdir(parents=True)
    (bad_dir / "card.yaml").write_text(
        "not: a: valid: yaml: shape: at: all", encoding="utf-8"
    )
    (bad_dir / "README.md").write_text("# bad\n", encoding="utf-8")
    with pytest.raises(CardError):
        loader.load_all_cards(project)


# ── Backward compatibility ──────────────────────────────────────────────────


def test_legacy_canon_only_root_still_works(tmp_path):
    """`load_all_cards(canon_root)` passada uma pasta sem `.claude/` permanece canon-only."""
    canon_root = tmp_path / "canon"
    canon_root.mkdir()
    _write_card_dir(canon_root / "demo", _valid_card_dict("demo"))
    manifests = loader.load_all_cards(canon_root)
    assert [m.name for m in manifests] == ["demo"]
    assert manifests[0].origin == "canon"
