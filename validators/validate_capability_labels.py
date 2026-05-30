#!/usr/bin/env python3
"""validate_capability_labels.py — Capability label catalog enforcement.

For every `cards/{name}/card.yaml` (or the snapshot under `.claude/cards/`),
validates that every label in `provides` / `requires` / `conflicts-with` is
present in the canonical catalog defined by
`docs/schemas/capability-labels.md`.

- Out-of-catalog labels → fail
- Reserved labels (still planned) → warn

Schema source: docs/schemas/capability-labels.md.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from _common import (
    make_paths,
    result_fail,
    result_pass,
    result_warn,
    run_cli,
)

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.cards.loader import (  # noqa: E402
    _get_catalog,
    _parse_capability_catalog,
)
from engine.utils.paths import (  # noqa: E402
    cards_canonical_dir,
    cards_dir,
    forge_home,
)
from engine.utils.yaml_io import read_yaml_or_default  # noqa: E402


def _collect_cards(project_root: Path) -> list[Path]:
    """Return all card.yaml files to validate (project snapshot + canonical)."""
    candidates: list[Path] = []
    snapshot = cards_dir(project_root)
    if snapshot.is_dir():
        candidates.extend(snapshot.glob("*/card.yaml"))
    if not candidates:
        canonical = cards_canonical_dir()
        if canonical.is_dir():
            candidates.extend(canonical.glob("*/card.yaml"))
    return sorted(candidates)


def _catalog() -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
    """Catalog (all, singular, latent). Hits the cached parse from engine."""
    try:
        return _get_catalog()
    except Exception:
        # Fall back to a direct parse — useful when cache is unset.
        catalog_path = forge_home() / "docs/schemas/capability-labels.md"
        return _parse_capability_catalog(catalog_path)


def _reserved_labels(all_labels: frozenset[str], singular: frozenset[str], latent: frozenset[str]) -> frozenset[str]:
    """Labels that exist in the catalog but are neither singular nor latent."""
    return frozenset(all_labels - singular - latent)


def validate(project_root: Path, **kwargs: Any) -> dict[str, Any]:
    """Validate every card's capability-label usage against the catalog."""
    cards = _collect_cards(project_root)
    if not cards:
        return result_warn(
            "nenhum card.yaml encontrado pra validar",
            what_failed="empty cards dir",
            where=str(cards_dir(project_root)),
            why=["forge init ainda não rodou, ou snapshot vazio"],
        )

    all_labels, singular, latent = _catalog()
    reserved = _reserved_labels(all_labels, singular, latent)

    failures: list[str] = []
    reserved_hits: list[str] = []
    cards_checked = 0

    for card_yaml in cards:
        cards_checked += 1
        try:
            data = read_yaml_or_default(card_yaml, {}) or {}
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{card_yaml.parent.name}: YAML parse error ({exc})")
            continue
        if not isinstance(data, dict):
            failures.append(f"{card_yaml.parent.name}: top-level not mapping")
            continue

        for block_name in ("provides", "requires", "conflicts-with"):
            block = data.get(block_name) or []
            if not isinstance(block, list):
                continue
            for label in block:
                if not isinstance(label, str) or not label:
                    continue
                if label not in all_labels:
                    failures.append(f"{card_yaml.parent.name}.{block_name}: {label!r} out-of-catalog")
                elif label in reserved:
                    reserved_hits.append(f"{card_yaml.parent.name}.{block_name}: {label!r} (reserved)")

    if failures:
        return result_fail(
            f"{len(failures)} label(s) out-of-catalog em {cards_checked} card(s)",
            what_failed="; ".join(failures[:3]) + (f" (+{len(failures)-3} more)" if len(failures) > 3 else ""),
            where="cards/*/card.yaml",
            why=[
                "capability-labels.md é source-of-truth (CARD-006/CARD-007).",
                "Labels fora do catálogo quebram resolução de cards.",
            ],
            paths=make_paths(
                "Adicionar a label ao docs/schemas/capability-labels.md (PR canônico)",
                "Catalog evolve via 1-file change; veja seção Reserved.",
                "Editar o card.yaml e usar uma label canônica equivalente",
                "Costuma haver um sinônimo no catalog.",
                "Marcar o card como experimental — `forge reconfigure → remover card`",
                "Se o card está deprecado, removê-lo evita o erro.",
            ),
        )

    if reserved_hits:
        return result_warn(
            f"{len(reserved_hits)} label(s) reservada(s) em uso — ainda não implementada(s)",
            what_failed="; ".join(reserved_hits[:3]),
            where="cards/*/card.yaml",
            why=["Labels reservadas são placeholder pra v1.1+"],
        )

    return result_pass(
        f"{cards_checked} card(s) com labels todas no catálogo canônico"
    )


def _extra_args(parser: Any) -> None:
    parser.add_argument("--card", required=False, help="Validate only this card name")


if __name__ == "__main__":
    sys.exit(run_cli(__doc__ or "", validate, extra_args=_extra_args))
