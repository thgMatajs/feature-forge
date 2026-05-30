"""Unit tests — engine.cards.loader.

Validates `load_card`, `load_all_cards`, the CARD-001..018 validation matrix
on synthetic card.yaml dicts, and the lazy capability catalog parser.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from engine.cards import CardError, loader


def _valid_card_dict() -> dict:
    return {
        "schema-version": 1,
        "identity": {
            "name": "valid-card",
            "version": "1.0.0",
            "description": "Test card",
            "category": "kmp",
            "maturity": "stable",
        },
        # Use a known canonical capability so CARD-006 passes against the catalog.
        "provides": ["kotlin-multiplatform"],
        "requires": [],
        "conflicts-with": [],
    }


def _write_card(dir_: Path, data: dict) -> None:
    """Write card.yaml + README.md so CARD-018 passes (README required)."""
    dir_.mkdir(parents=True, exist_ok=True)
    (dir_ / "card.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    (dir_ / "README.md").write_text("# test card\n", encoding="utf-8")


def test_load_card_happy_path_uses_canonical_card(forge_home):
    card_dir = forge_home / "cards" / "kmp-shared"
    manifest = loader.load_card(card_dir)
    assert manifest.name == "kmp-shared"
    assert manifest.version == "1.0.0"
    assert manifest.category == "kmp"
    assert "kotlin-multiplatform" in manifest.provides


def test_load_card_missing_file_raises(tmp_path):
    with pytest.raises(CardError) as exc:
        loader.load_card(tmp_path)
    assert "card.yaml not found" in str(exc.value)


def test_load_all_cards_skips_hidden_dirs(tmp_path):
    _write_card(tmp_path / "good", _valid_card_dict())
    archived_dir = tmp_path / ".archived"
    _write_card(archived_dir, _valid_card_dict())
    manifests = loader.load_all_cards(tmp_path)
    assert [m.name for m in manifests] == ["valid-card"]


def test_load_all_cards_sorted_by_name(tmp_path):
    d1 = _valid_card_dict()
    d1["identity"]["name"] = "zeta"
    d2 = _valid_card_dict()
    d2["identity"]["name"] = "alpha"
    _write_card(tmp_path / "zeta", d1)
    _write_card(tmp_path / "alpha", d2)
    names = [m.name for m in loader.load_all_cards(tmp_path)]
    assert names == ["alpha", "zeta"]


def test_validate_card_yaml_returns_no_violations_for_valid():
    violations = loader.validate_card_yaml(_valid_card_dict(), Path("."))
    # Some violations may come from cross-cutting checks (provides/requires
    # vs catalog) but identity/version/maturity violations should not appear.
    assert not any(v.startswith("CARD-001") for v in violations)
    assert not any(v.startswith("CARD-002") for v in violations)
    assert not any(v.startswith("CARD-003") for v in violations)


def test_validate_card_yaml_card_001_wrong_schema_version():
    bad = _valid_card_dict()
    bad["schema-version"] = 99
    violations = loader.validate_card_yaml(bad, Path("."))
    assert any("CARD-001" in v for v in violations)


def test_validate_card_yaml_card_002_invalid_name():
    bad = _valid_card_dict()
    bad["identity"]["name"] = "INVALID NAME WITH SPACES"
    violations = loader.validate_card_yaml(bad, Path("."))
    assert any("CARD-002" in v for v in violations)


def test_validate_card_yaml_card_003_invalid_semver():
    bad = _valid_card_dict()
    bad["identity"]["version"] = "not-a-version"
    violations = loader.validate_card_yaml(bad, Path("."))
    assert any("CARD-003" in v for v in violations)


def test_validate_card_yaml_card_004_unknown_category():
    bad = _valid_card_dict()
    bad["identity"]["category"] = "fictional-category"
    violations = loader.validate_card_yaml(bad, Path("."))
    assert any("CARD-004" in v for v in violations)


def test_validate_card_yaml_card_005_invalid_maturity():
    bad = _valid_card_dict()
    bad["identity"]["maturity"] = "shiny"
    violations = loader.validate_card_yaml(bad, Path("."))
    assert any("CARD-005" in v for v in violations)


def test_parse_capability_catalog_known_labels(forge_home):
    loader._reset_catalog_cache()
    all_labels = loader._get_catalog()[0]
    assert isinstance(all_labels, frozenset)
    assert len(all_labels) > 5
    # singular labels must be a subset of all
    singular = loader.known_singular_labels()
    assert singular.issubset(all_labels)


def test_known_latent_labels_returns_frozenset(forge_home):
    loader._reset_catalog_cache()
    latent = loader.known_latent_labels()
    assert isinstance(latent, frozenset)
