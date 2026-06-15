"""Tests for validators/validate_presets.py — schema validation of bundle YAMLs.

Validator-under-test: validators/validate_presets.py.

Bundle YAMLs live em `presets/<preset-name>/bundles/<bundle>.yaml` e descrevem
defaults per-(axis, platform) consumidos pelo init flow (W7). Os 8 axes e 4
platforms canônicos vêm de `docs/schemas/backend-axes.md`.

Cobertura TDD para AC-3 do SPEC det-6-multi-axis-backend:
- happy-path: bundles reais validam
- axis unknown rejeitado
- campo obrigatório ausente rejeitado
- card reference inexistente rejeitado
- platform key unknown rejeitado
- valores não-string/non-null no slot de card rejeitados
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from validators.validate_presets import (
    BundleValidationError,
    validate_bundle,
    validate_bundle_file,
)


# ── Helpers ────────────────────────────────────────────────────────────────


def _write_yaml(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def _make_fake_cards_dir(tmp_path: Path, names: list[str]) -> Path:
    """Cria um cards/ dir sintético: cada card é uma pasta com card.yaml stub."""
    root = tmp_path / "cards"
    for name in names:
        (root / name).mkdir(parents=True, exist_ok=True)
        (root / name / "card.yaml").write_text(
            f"identity:\n  name: {name}\n", encoding="utf-8"
        )
    return root


def _minimal_valid_bundle() -> dict:
    """Bundle minimamente válido (todos slots null exceto persistence-android)."""
    return {
        "schema-version": 1,
        "name": "fixture-bundle",
        "description": "fixture-only",
        "defaults": {
            "data": {"all-platforms": None},
            "auth": {"all-platforms": None},
            "observability": {"all-platforms": None},
            "analytics": {"all-platforms": None},
            "storage": {"all-platforms": None},
            "persistence": {
                "android": "stub-card",
                "ios": None,
                "kmp": None,
            },
            "notifications": {"all-platforms": None},
            "flags": {"all-platforms": None},
        },
    }


# ── RED tests (RED → GREEN cycle) ──────────────────────────────────────────


def test_happy_path_minimal_bundle_validates(tmp_path):
    """Bundle válido com todos os 8 axes presentes não levanta."""
    cards_dir = _make_fake_cards_dir(tmp_path, ["stub-card"])
    validate_bundle(_minimal_valid_bundle(), cards_dir=cards_dir)


def test_rejects_unknown_axis(tmp_path):
    """Axis fora do enum de 8 canônicos → erro."""
    cards_dir = _make_fake_cards_dir(tmp_path, ["stub-card"])
    bundle = _minimal_valid_bundle()
    bundle["defaults"]["data2"] = {"all-platforms": None}  # axis inválido
    with pytest.raises(BundleValidationError, match=r"(?i)unknown axis"):
        validate_bundle(bundle, cards_dir=cards_dir)


def test_rejects_missing_name(tmp_path):
    """Campo `name` ausente → erro."""
    cards_dir = _make_fake_cards_dir(tmp_path, ["stub-card"])
    bundle = _minimal_valid_bundle()
    del bundle["name"]
    with pytest.raises(BundleValidationError, match=r"(?i)name"):
        validate_bundle(bundle, cards_dir=cards_dir)


def test_rejects_missing_description(tmp_path):
    """Campo `description` ausente → erro."""
    cards_dir = _make_fake_cards_dir(tmp_path, ["stub-card"])
    bundle = _minimal_valid_bundle()
    del bundle["description"]
    with pytest.raises(BundleValidationError, match=r"(?i)description"):
        validate_bundle(bundle, cards_dir=cards_dir)


def test_rejects_missing_defaults(tmp_path):
    """Campo `defaults` ausente → erro."""
    cards_dir = _make_fake_cards_dir(tmp_path, ["stub-card"])
    bundle = _minimal_valid_bundle()
    del bundle["defaults"]
    with pytest.raises(BundleValidationError, match=r"(?i)defaults"):
        validate_bundle(bundle, cards_dir=cards_dir)


def test_rejects_unknown_card_reference(tmp_path):
    """Referência a card inexistente → erro."""
    cards_dir = _make_fake_cards_dir(tmp_path, ["stub-card"])
    bundle = _minimal_valid_bundle()
    bundle["defaults"]["data"] = {"all-platforms": "nonexistent-card"}
    with pytest.raises(
        BundleValidationError, match=r"(?i)card.*(does not exist|not found|nonexistent)"
    ):
        validate_bundle(bundle, cards_dir=cards_dir)


def test_rejects_unknown_platform_key(tmp_path):
    """Platform key fora do enum {android, ios, kmp, all-platforms} → erro."""
    cards_dir = _make_fake_cards_dir(tmp_path, ["stub-card"])
    bundle = _minimal_valid_bundle()
    bundle["defaults"]["data"] = {"windows": "stub-card"}
    with pytest.raises(BundleValidationError, match=r"(?i)platform"):
        validate_bundle(bundle, cards_dir=cards_dir)


def test_rejects_non_string_card_value(tmp_path):
    """Valor não-string/non-null no slot de card → erro."""
    cards_dir = _make_fake_cards_dir(tmp_path, ["stub-card"])
    bundle = _minimal_valid_bundle()
    bundle["defaults"]["data"] = {"all-platforms": 42}  # tipo inválido
    with pytest.raises(BundleValidationError, match=r"(?i)card.*(string|null)"):
        validate_bundle(bundle, cards_dir=cards_dir)


def test_rejects_missing_axis(tmp_path):
    """Algum dos 8 axes obrigatórios ausente → erro."""
    cards_dir = _make_fake_cards_dir(tmp_path, ["stub-card"])
    bundle = _minimal_valid_bundle()
    del bundle["defaults"]["flags"]
    with pytest.raises(BundleValidationError, match=r"(?i)flags|missing axis"):
        validate_bundle(bundle, cards_dir=cards_dir)


def test_accepts_all_platforms_shorthand(tmp_path):
    """Shorthand `all-platforms: <card>` é forma válida."""
    cards_dir = _make_fake_cards_dir(tmp_path, ["stub-card", "my-card"])
    bundle = _minimal_valid_bundle()
    bundle["defaults"]["data"] = {"all-platforms": "my-card"}
    validate_bundle(bundle, cards_dir=cards_dir)  # no raise


def test_accepts_platform_keyed_form(tmp_path):
    """Forma platform-keyed `{android: X, ios: Y, kmp: Z}` é válida."""
    cards_dir = _make_fake_cards_dir(tmp_path, ["stub-card", "a", "b"])
    bundle = _minimal_valid_bundle()
    bundle["defaults"]["data"] = {"android": "a", "ios": None, "kmp": "b"}
    validate_bundle(bundle, cards_dir=cards_dir)  # no raise


def test_validate_bundle_file_parses_yaml(tmp_path):
    """`validate_bundle_file` lê YAML do disco e valida."""
    cards_dir = _make_fake_cards_dir(tmp_path, ["stub-card"])
    bundle_path = _write_yaml(
        tmp_path / "bundle.yaml", _minimal_valid_bundle()
    )
    validate_bundle_file(bundle_path, cards_dir=cards_dir)  # no raise


def test_validate_bundle_file_rejects_invalid_yaml(tmp_path):
    """Bundle file com YAML malformado → erro com path."""
    cards_dir = _make_fake_cards_dir(tmp_path, ["stub-card"])
    bad = tmp_path / "broken.yaml"
    bad.write_text("not: valid: yaml: [\n", encoding="utf-8")
    with pytest.raises(BundleValidationError, match=r"(?i)yaml|parse"):
        validate_bundle_file(bad, cards_dir=cards_dir)


# ── Smoke happy-path: bundles reais do projeto ─────────────────────────────


REAL_BUNDLES_DIR = (
    Path(__file__).resolve().parents[2] / "presets" / "kmp-mobile" / "bundles"
)
REAL_CARDS_DIR = Path(__file__).resolve().parents[2] / "cards"


@pytest.mark.parametrize(
    "bundle_name",
    ["firebase-full", "rest-with-firebase-telemetry", "local-only"],
)
def test_real_bundles_pass_validation(bundle_name):
    """Os 3 bundles canônicos criados em W6.1 validam contra cards/ real."""
    bundle_path = REAL_BUNDLES_DIR / f"{bundle_name}.yaml"
    assert bundle_path.exists(), f"missing real bundle: {bundle_path}"
    validate_bundle_file(bundle_path, cards_dir=REAL_CARDS_DIR)
