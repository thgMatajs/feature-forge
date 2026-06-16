"""Unit tests — validate_card_yaml.py overlay-aware.

Cobre:
  - canon vs local discrimination via path resolved
  - colisão de nome canon ∩ local → hard fail
  - `legacy-marker: true` aceito (sem CARD-019)
  - `legacy-marker: "yes"` rejeitado (CARD-019, deve ser bool)
  - mensagens carregam contexto [canon] / [local]
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
VALIDATORS_DIR = REPO_ROOT / "validators"
if str(VALIDATORS_DIR) not in sys.path:
    sys.path.insert(0, str(VALIDATORS_DIR))


def _valid_card_dict(name: str = "demo-card", **overrides) -> dict:
    base = {
        "schema-version": 1,
        "identity": {
            "name": name,
            "version": "1.0.0",
            "description": "Test",
            "category": "kmp",
            "maturity": "stable",
        },
        "provides": ["kotlin-multiplatform"],
        "requires": [],
        "conflicts-with": [],
    }
    base.update(overrides)
    return base


def _write_card(card_dir: Path, data: dict) -> None:
    card_dir.mkdir(parents=True, exist_ok=True)
    (card_dir / "card.yaml").write_text(
        yaml.safe_dump(data, sort_keys=False), encoding="utf-8"
    )
    (card_dir / "README.md").write_text("# test\n", encoding="utf-8")


def _build_project_with_cards(
    tmp_path: Path,
    canon: dict[str, dict] | None = None,
    local: dict[str, dict] | None = None,
) -> Path:
    """Task 0.8 (v1.3): local overlay agora vive em ``.claude/forge/cards/local/``.

    Canon snapshot continua em ``.claude/cards/`` — só o overlay migrou
    pro sub-namespace.
    """
    project = tmp_path / "proj"
    cards_root = project / ".claude" / "cards"
    cards_root.mkdir(parents=True)
    if canon:
        for name, data in canon.items():
            _write_card(cards_root / name, data)
    if local:
        local_root = project / ".claude" / "forge" / "cards" / "local"
        local_root.mkdir(parents=True, exist_ok=True)
        for name, data in local.items():
            _write_card(local_root / name, data)
    return project


@pytest.fixture
def vcy_module():
    import validate_card_yaml as vcy
    return importlib.reload(vcy)


# ── Path discrimination ─────────────────────────────────────────────────────


def test_canon_card_tagged_canon_in_collection(vcy_module, tmp_path):
    project = _build_project_with_cards(
        tmp_path,
        canon={"alpha": _valid_card_dict("alpha")},
    )
    collected = vcy_module._collect_cards(project)
    origins = {(p.parent.name, o) for p, o in collected}
    assert ("alpha", "canon") in origins


def test_local_card_tagged_local_in_collection(vcy_module, tmp_path):
    project = _build_project_with_cards(
        tmp_path,
        canon={"alpha": _valid_card_dict("alpha")},
        local={"beta": _valid_card_dict("beta")},
    )
    collected = vcy_module._collect_cards(project)
    origins = {(p.parent.name, o) for p, o in collected}
    assert ("alpha", "canon") in origins
    assert ("beta", "local") in origins


# ── Colisão ─────────────────────────────────────────────────────────────────


def test_canon_local_name_collision_hard_fails(vcy_module, tmp_path):
    project = _build_project_with_cards(
        tmp_path,
        canon={"collide": _valid_card_dict("collide")},
        local={"collide": _valid_card_dict("collide")},
    )
    result = vcy_module.validate(project)
    assert result["status"] == "fail"
    assert "colisão" in (result.get("what-failed") or "").lower() or "collide" in (
        result.get("what-failed") or ""
    )


# ── legacy-marker aceito ────────────────────────────────────────────────────


def test_legacy_marker_true_accepted(vcy_module, tmp_path):
    data = _valid_card_dict("legacy-x")
    data["legacy-marker"] = True
    project = _build_project_with_cards(tmp_path, canon={"legacy-x": data})
    result = vcy_module.validate(project)
    # Pode passar (status=pass) ou warn por CARD-013-WARN; o que importa é
    # que NÃO há violação CARD-019 sobre legacy-marker.
    assert result["status"] in ("pass", "warn")
    what = (result.get("what-failed") or "")
    assert "CARD-019" not in what
    assert "legacy-marker" not in what.lower()


def test_legacy_marker_absent_accepted(vcy_module, tmp_path):
    """Default ausente = false, não dispara CARD-019."""
    project = _build_project_with_cards(
        tmp_path, canon={"plain": _valid_card_dict("plain")}
    )
    result = vcy_module.validate(project)
    assert result["status"] in ("pass", "warn")
    assert "CARD-019" not in (result.get("what-failed") or "")


def test_legacy_marker_non_bool_rejected(vcy_module, tmp_path):
    data = _valid_card_dict("bad-marker")
    data["legacy-marker"] = "yes"  # string, não bool
    project = _build_project_with_cards(tmp_path, canon={"bad-marker": data})
    result = vcy_module.validate(project)
    assert result["status"] == "fail"
    assert "CARD-019" in (result.get("what-failed") or "")


# ── Mensagens com contexto ──────────────────────────────────────────────────


def test_local_card_error_messages_carry_local_tag(vcy_module, tmp_path):
    bad_local = _valid_card_dict("bad")
    bad_local["identity"]["version"] = "not-semver"
    project = _build_project_with_cards(
        tmp_path,
        canon={"alpha": _valid_card_dict("alpha")},
        local={"bad": bad_local},
    )
    result = vcy_module.validate(project)
    assert result["status"] == "fail"
    what = result.get("what-failed") or ""
    assert "[local]" in what
    assert "CARD-003" in what
