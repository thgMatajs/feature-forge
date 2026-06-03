"""Unit tests — validate_capability_labels.conflicts-with aceita card-name.

Cobre o gap N1 do power-review PR #2: per schema CARD-008
(docs/schemas/card.md), o bloco `conflicts-with` aceita capability labels
OR specific card names. A versão anterior do validator rejeitava
nomes-de-card por não estarem no catálogo de labels — quebrava cards
canon como `shared-preferences-prefs` (que conflita com `datastore-prefs`
via card-name).

Cobre:
  (a) card-name válido em conflicts-with → pass
  (b) label válida em conflicts-with → pass
  (c) nome desconhecido (nem label, nem card) → fail
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

# Bootstrap path para `from _common import ...` (validators dir não é pacote).
_REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATORS_DIR = _REPO_ROOT / "validators"
if str(_VALIDATORS_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATORS_DIR))


def _valid_card_dict(
    name: str,
    *,
    provides: list[str] | None = None,
    conflicts_with: list[str] | None = None,
) -> dict:
    return {
        "schema-version": 1,
        "identity": {
            "name": name,
            "version": "1.0.0",
            "description": "Test",
            "category": "kmp",
            "maturity": "stable",
        },
        "provides": provides or ["kotlin-multiplatform"],
        "requires": [],
        "conflicts-with": conflicts_with or [],
    }


def _write_card(card_dir: Path, data: dict) -> None:
    card_dir.mkdir(parents=True, exist_ok=True)
    (card_dir / "card.yaml").write_text(
        yaml.safe_dump(data, sort_keys=False), encoding="utf-8"
    )
    (card_dir / "README.md").write_text("# test\n", encoding="utf-8")


def _build_project(tmp_path: Path, cards: dict[str, dict]) -> Path:
    project = tmp_path / "proj"
    cards_root = project / ".claude" / "cards"
    cards_root.mkdir(parents=True)
    for name, data in cards.items():
        _write_card(cards_root / name, data)
    return project


@pytest.fixture
def vcl_module():
    import importlib
    import validate_capability_labels as vcl
    return importlib.reload(vcl)


def test_conflicts_with_accepts_card_name(vcl_module, tmp_path):
    """Card-name reference em conflicts-with deve passar (CARD-008)."""
    project = _build_project(
        tmp_path,
        cards={
            "datastore-prefs": _valid_card_dict("datastore-prefs"),
            "shared-preferences-prefs": _valid_card_dict(
                "shared-preferences-prefs",
                conflicts_with=["datastore-prefs"],  # card-name ref, NÃO label
            ),
        },
    )
    result = vcl_module.validate(project)
    assert result["status"] in ("pass", "warn"), (
        f"esperado pass/warn, got {result['status']}: {result.get('what-failed')}"
    )
    assert "out-of-catalog" not in (result.get("what-failed") or "")


def test_conflicts_with_accepts_capability_label(vcl_module, tmp_path):
    """Label canônica em conflicts-with deve passar (caminho legacy intacto)."""
    project = _build_project(
        tmp_path,
        cards={
            "card-a": _valid_card_dict(
                "card-a",
                provides=["kotlin-multiplatform"],
                # `swift-language` é label canon — válida como conflict label
                conflicts_with=["swift-language"],
            ),
        },
    )
    result = vcl_module.validate(project)
    assert result["status"] in ("pass", "warn"), (
        f"esperado pass/warn, got {result['status']}: {result.get('what-failed')}"
    )


def test_conflicts_with_rejects_unknown_name(vcl_module, tmp_path):
    """Nome que não é label nem card-name deve falhar com mensagem clara."""
    project = _build_project(
        tmp_path,
        cards={
            "card-a": _valid_card_dict(
                "card-a",
                conflicts_with=["bogus-not-label-not-card-name-12345"],
            ),
        },
    )
    result = vcl_module.validate(project)
    assert result["status"] == "fail"
    what = result.get("what-failed") or ""
    assert "bogus-not-label-not-card-name-12345" in what
