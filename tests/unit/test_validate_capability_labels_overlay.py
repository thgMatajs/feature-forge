"""Unit tests — validate_capability_labels overlay-aware via load_catalog.

Cobre:
  - união canon ∪ local (label local válida não dispara out-of-catalog)
  - promoção reservada rejeitada (CatalogOverlayError)
  - colisão active rejeitada (CatalogOverlayError)
  - overlay vazio = canon-only silent
  - YAML malformado (CatalogOverlayError)
  - chaves proibidas (overrides / reserved-promotions)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

# Bootstrap path para `from _common import ...` (validators dir não é pacote).
_VALIDATORS_DIR = Path(__file__).resolve().parents[2] / "validators"
if str(_VALIDATORS_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATORS_DIR))

from _common import CatalogOverlayError, load_catalog  # noqa: E402
from engine.cards.loader import _reset_catalog_cache  # noqa: E402


def _project_with_overlay(tmp_path: Path, overlay_data: dict | str | None) -> Path:
    """Mount fake project root with `.claude/inventory/` ready for overlay testing."""
    project = tmp_path / "proj"
    inv = project / ".claude" / "inventory"
    inv.mkdir(parents=True)
    if overlay_data is None:
        return project
    overlay_path = inv / "capability-labels.local.yaml"
    if isinstance(overlay_data, str):
        # raw string mode — permite YAML malformado deliberado
        overlay_path.write_text(overlay_data, encoding="utf-8")
    else:
        overlay_path.write_text(
            yaml.safe_dump(overlay_data, sort_keys=False), encoding="utf-8"
        )
    return project


@pytest.fixture(autouse=True)
def _fresh_catalog():
    _reset_catalog_cache()
    yield
    _reset_catalog_cache()


# ── Happy paths ─────────────────────────────────────────────────────────────


def test_overlay_absent_returns_canon_only(tmp_path):
    project = _project_with_overlay(tmp_path, None)
    catalog = load_catalog(project)
    assert isinstance(catalog.active, frozenset)
    assert len(catalog.active) > 5  # canon is non-empty
    assert catalog.local_added == frozenset()


def test_overlay_adds_local_label(tmp_path):
    project = _project_with_overlay(
        tmp_path,
        {
            "schema-version": 1,
            "added": [
                {
                    "name": "feature-flag-remote",
                    "description": "LaunchDarkly + Firebase Remote Config",
                    "target-platforms": ["android", "ios"],
                }
            ],
        },
    )
    catalog = load_catalog(project)
    assert "feature-flag-remote" in catalog.active
    assert "feature-flag-remote" in catalog.local_added


def test_overlay_empty_added_is_canon_only(tmp_path):
    project = _project_with_overlay(tmp_path, {"schema-version": 1, "added": []})
    catalog = load_catalog(project)
    assert catalog.local_added == frozenset()


# ── Guards ──────────────────────────────────────────────────────────────────


def test_overlay_rejects_promotion_of_reserved_label(tmp_path):
    """Labels reservadas no canon não podem ser ativadas via overlay."""
    # Pick a reservada que já existe — `graphql-client` está em
    # capability-labels.md como reservada v1.1+ (sem provider canon). Se
    # renomearem ou promoverem no canon, este test quebra (esperado).
    project = _project_with_overlay(
        tmp_path,
        {
            "schema-version": 1,
            "added": [
                {"name": "graphql-client", "description": "promovendo reservada"}
            ],
        },
    )
    with pytest.raises(CatalogOverlayError) as exc:
        load_catalog(project)
    assert "reservada" in str(exc.value).lower() or "promoção" in str(exc.value).lower()


def test_overlay_rejects_collision_with_canon_active(tmp_path):
    project = _project_with_overlay(
        tmp_path,
        {
            "schema-version": 1,
            "added": [{"name": "kotlin", "description": "tentando override"}],
        },
    )
    with pytest.raises(CatalogOverlayError) as exc:
        load_catalog(project)
    assert "colide" in str(exc.value).lower() or "canon ativo" in str(exc.value).lower()


def test_overlay_rejects_forbidden_keys(tmp_path):
    project = _project_with_overlay(
        tmp_path,
        {
            "schema-version": 1,
            "added": [],
            "overrides": [{"name": "kotlin", "to": "kotlin-2"}],
        },
    )
    with pytest.raises(CatalogOverlayError) as exc:
        load_catalog(project)
    assert "overrides" in str(exc.value)


def test_overlay_rejects_reserved_promotions_key(tmp_path):
    project = _project_with_overlay(
        tmp_path,
        {
            "schema-version": 1,
            "added": [],
            "reserved-promotions": ["hilt-di"],
        },
    )
    with pytest.raises(CatalogOverlayError) as exc:
        load_catalog(project)
    assert "reserved-promotions" in str(exc.value)


def test_overlay_rejects_malformed_yaml(tmp_path):
    project = _project_with_overlay(
        tmp_path, "added: [not: a: valid: list: shape:"
    )
    with pytest.raises(CatalogOverlayError):
        load_catalog(project)


def test_overlay_rejects_non_mapping_toplevel(tmp_path):
    project = _project_with_overlay(tmp_path, "just a string")
    with pytest.raises(CatalogOverlayError) as exc:
        load_catalog(project)
    assert "mapping" in str(exc.value).lower()


def test_overlay_rejects_added_without_name(tmp_path):
    project = _project_with_overlay(
        tmp_path,
        {
            "schema-version": 1,
            "added": [{"description": "no name field"}],
        },
    )
    with pytest.raises(CatalogOverlayError) as exc:
        load_catalog(project)
    assert "name" in str(exc.value).lower()
