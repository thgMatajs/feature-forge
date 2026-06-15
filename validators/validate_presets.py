#!/usr/bin/env python3
"""validate_presets.py — schema validation pra bundle YAMLs de preset.

Bundle YAMLs vivem em `presets/<preset>/bundles/<bundle>.yaml` e descrevem
defaults per-(axis, platform) consumidos pelo init flow (W7 — det-6).

Schema canônico:
- schema-version: 1
- name: string
- description: string
- defaults: mapa de 8 axes (data, auth, observability, analytics, storage,
  persistence, notifications, flags), cada um mapa de platform → card-name|null.
  Platform keys: {android, ios, kmp, all-platforms}.

Cada card referenciado tem que existir em `cards/<name>/card.yaml`.

Interface: library raise-based (mesmo pattern de validate_qa_finding) +
CLI entry via `_common.run_cli` pra futura inclusão na cascade de
`forge verify` / `forge doctor` (registro em engine/verify.py é trabalho
separado, fora do escopo W6.3).

Schema fonte: docs/schemas/backend-axes.md + SPEC det-6-multi-axis-backend
§Starter bundles.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

# Package-import resolution: tests import as ``from validators.validate_presets
# import …`` which sets ``__package__ = "validators"``; CLI/script execution
# (``python validators/validate_presets.py``) needs the project root on
# ``sys.path`` so the same absolute import works. Doing the path insert
# unconditionally (and idempotently) is simpler than maintaining two branches
# of imports — PR #13 review #3405254868 flagged the prior dual-branch as
# noise. The insert is a no-op when the project root is already discoverable
# (normal package install OR pytest rootdir).
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from validators._common import (  # noqa: E402
    VALID_BACKEND_AXES,
    VALID_BUNDLE_PLATFORM_KEYS,
    make_paths,
    result_fail,
    result_pass,
    result_warn,
    run_cli,
)


class BundleValidationError(ValueError):
    """Bundle YAML não cumpre o schema v1."""


# Re-export pros nomes locais que tests e callers já consomem
# (PR #13 review #3405255016 — fonte canônica agora em validators._common).
VALID_AXES: frozenset[str] = VALID_BACKEND_AXES
VALID_PLATFORMS: frozenset[str] = VALID_BUNDLE_PLATFORM_KEYS

_REQUIRED_TOP_LEVEL = ("name", "description", "defaults")


# ── Internal helpers ────────────────────────────────────────────────────────


def _check_required_fields(bundle: dict[str, Any]) -> None:
    for key in _REQUIRED_TOP_LEVEL:
        if key not in bundle:
            raise BundleValidationError(
                f"bundle missing required field '{key}'"
            )
        if bundle[key] is None:
            raise BundleValidationError(
                f"bundle field '{key}' is null; expected non-empty value"
            )


def _check_defaults_shape(defaults: Any) -> None:
    if not isinstance(defaults, dict):
        raise BundleValidationError(
            f"bundle field 'defaults' must be a mapping; got {type(defaults).__name__}"
        )


def _check_axes_complete(defaults: dict[str, Any]) -> None:
    declared = set(defaults.keys())
    unknown = declared - VALID_AXES
    if unknown:
        raise BundleValidationError(
            f"unknown axis (axes) in defaults: {sorted(unknown)}; "
            f"valid axes are {sorted(VALID_AXES)}"
        )
    missing = VALID_AXES - declared
    if missing:
        raise BundleValidationError(
            f"missing axis (axes) in defaults: {sorted(missing)}; "
            f"every bundle must declare all 8 canonical axes"
        )


def _check_axis_slot(
    axis: str, slot: Any, *, cards_dir: Path, card_cache: set[str]
) -> None:
    if not isinstance(slot, dict):
        raise BundleValidationError(
            f"axis '{axis}' value must be a mapping of platform→card; "
            f"got {type(slot).__name__}"
        )
    for platform_key, card_value in slot.items():
        if platform_key not in VALID_PLATFORMS:
            raise BundleValidationError(
                f"axis '{axis}': unknown platform key '{platform_key}'; "
                f"valid platforms are {sorted(VALID_PLATFORMS)}"
            )
        if card_value is None:
            continue  # opt-out explícito é válido
        if not isinstance(card_value, str):
            raise BundleValidationError(
                f"axis '{axis}' platform '{platform_key}': card value must be "
                f"a string (card name) or null; got {type(card_value).__name__}"
            )
        _check_card_exists(
            axis=axis,
            platform_key=platform_key,
            card_name=card_value,
            cards_dir=cards_dir,
            card_cache=card_cache,
        )


def _check_card_exists(
    *,
    axis: str,
    platform_key: str,
    card_name: str,
    cards_dir: Path,
    card_cache: set[str],
) -> None:
    if card_name in card_cache:
        return
    card_yaml = cards_dir / card_name / "card.yaml"
    if not card_yaml.is_file():
        raise BundleValidationError(
            f"axis '{axis}' platform '{platform_key}': referenced card "
            f"'{card_name}' does not exist (expected {card_yaml})"
        )
    card_cache.add(card_name)


# ── Public API ──────────────────────────────────────────────────────────────


def validate_bundle(
    bundle: dict[str, Any],
    *,
    cards_dir: Path,
) -> None:
    """Valida shape individual de um bundle (já parseado).

    Args:
        bundle: dict parseado do bundle YAML.
        cards_dir: diretório contendo `<name>/card.yaml` por card.

    Raises:
        BundleValidationError: em qualquer desvio do schema v1.
    """
    if not isinstance(bundle, dict):
        raise BundleValidationError(
            f"bundle root must be a mapping; got {type(bundle).__name__}"
        )

    _check_required_fields(bundle)

    if not isinstance(bundle["name"], str) or not bundle["name"].strip():
        raise BundleValidationError(
            "bundle field 'name' must be a non-empty string"
        )
    if not isinstance(bundle["description"], str) or not bundle["description"].strip():
        raise BundleValidationError(
            "bundle field 'description' must be a non-empty string"
        )

    defaults = bundle["defaults"]
    _check_defaults_shape(defaults)
    _check_axes_complete(defaults)

    card_cache: set[str] = set()
    for axis, slot in defaults.items():
        _check_axis_slot(axis, slot, cards_dir=cards_dir, card_cache=card_cache)


def validate_bundle_file(
    bundle_path: Path,
    *,
    cards_dir: Path,
) -> None:
    """Lê YAML do disco e valida.

    Args:
        bundle_path: caminho para o bundle .yaml.
        cards_dir: diretório contendo `<name>/card.yaml` por card.

    Raises:
        BundleValidationError: YAML inválido ou shape fora do schema v1.
    """
    if not bundle_path.is_file():
        raise BundleValidationError(
            f"bundle file does not exist: {bundle_path}"
        )
    try:
        data = yaml.safe_load(bundle_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise BundleValidationError(
            f"failed to parse YAML at {bundle_path}: {exc}"
        ) from exc
    if data is None:
        raise BundleValidationError(
            f"bundle file is empty: {bundle_path}"
        )
    validate_bundle(data, cards_dir=cards_dir)


# ── CLI entry (cascade-compatible) ──────────────────────────────────────────


def _discover_bundles(project_root: Path) -> list[tuple[Path, Path]]:
    """Retorna lista de (bundle_yaml, cards_dir) por preset descoberto.

    Conventions:
    - presets/<preset>/bundles/*.yaml — bundles do preset
    - cards/ na raiz do projeto = cards canônicos
    """
    pairs: list[tuple[Path, Path]] = []
    cards_dir = project_root / "cards"
    presets_dir = project_root / "presets"
    if not presets_dir.is_dir():
        return pairs
    for preset_dir in sorted(presets_dir.iterdir()):
        bundles_dir = preset_dir / "bundles"
        if not bundles_dir.is_dir():
            continue
        for bundle in sorted(bundles_dir.glob("*.yaml")):
            pairs.append((bundle, cards_dir))
    return pairs


def validate(project_root: Path, **kwargs: Any) -> dict[str, Any]:
    """Cascade-shape entry: roda validate_bundle_file em todos bundles.

    Para uso em `forge verify` / `forge doctor`. Retorna result-dict
    (pass/warn/fail) per _common convention.
    """
    bundles = _discover_bundles(project_root)
    if not bundles:
        return result_warn(
            "nenhum bundle encontrado",
            what_failed="empty bundles dir",
            where=str(project_root / "presets" / "*" / "bundles"),
            why=[
                "Esperado pelo menos um preset com bundles/ populado",
                "Cobertura AC-3 do SPEC det-6 exige bundles canônicos",
            ],
            paths=make_paths(
                "Criar bundles canônicos",
                "Popular presets/<preset>/bundles/ com starter bundles",
                "Skip esta validação",
                "Marcar projeto como sem preset multi-axis",
                "Investigar layout",
                "Confirmar onde os presets vivem neste projeto",
            ),
        )

    failures: list[str] = []
    for bundle_path, cards_dir in bundles:
        try:
            validate_bundle_file(bundle_path, cards_dir=cards_dir)
        except BundleValidationError as exc:
            failures.append(f"{bundle_path}: {exc}")

    if failures:
        joined = "; ".join(failures)
        return result_fail(
            f"{len(failures)} bundle(s) inválido(s)",
            what_failed="bundle schema violations",
            where=joined,
            why=[
                "Bundles consumidos por forge init (W7) precisam de schema válido",
                "Cards referenciados precisam existir em cards/<name>/card.yaml",
            ],
            paths=make_paths(
                "Corrigir bundles",
                "Aplicar fix forward no schema do bundle",
                "Reverter bundles",
                "Remover bundles inválidos até o card ref existir",
                "Promover card faltante",
                "Criar card referenciado antes de re-validar",
            ),
        )

    return result_pass(f"{len(bundles)} bundle(s) válido(s)")


def main() -> int:
    return run_cli(__doc__ or "", validate)


if __name__ == "__main__":
    raise SystemExit(main())
