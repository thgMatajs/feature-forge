#!/usr/bin/env python3
"""validate_card_yaml.py — Thin wrapper over engine.cards.loader.validate_card_yaml.

Validates one (--card NAME) or all card.yaml files under either the project's
snapshot (`.claude/cards/`) or the canonical library (`cards/`).
Surfaces every CARD-001..CARD-018 violation.

Schema source: docs/schemas/card.md §Validation.
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

from engine.cards.loader import validate_card_yaml as core_validate  # noqa: E402
from engine.utils.paths import cards_canonical_dir, cards_dir  # noqa: E402
from engine.utils.yaml_io import read_yaml_or_default  # noqa: E402


def _collect_cards(project_root: Path, only: str | None = None) -> list[Path]:
    """Snapshot-first; fall back to canonical library when snapshot is empty."""
    candidates: list[Path] = []
    snapshot = cards_dir(project_root)
    if snapshot.is_dir():
        candidates.extend(snapshot.glob("*/card.yaml"))
    if not candidates:
        canonical = cards_canonical_dir()
        if canonical.is_dir():
            candidates.extend(canonical.glob("*/card.yaml"))
    if only:
        candidates = [c for c in candidates if c.parent.name == only]
    return sorted(candidates)


def validate(project_root: Path, **kwargs: Any) -> dict[str, Any]:
    """Run engine.cards.loader.validate_card_yaml against every card."""
    only = kwargs.get("card")
    cards = _collect_cards(project_root, only=only)
    if not cards:
        target = f"card={only!r}" if only else "any"
        return result_warn(
            f"nenhum card.yaml encontrado (filter: {target})",
            what_failed="empty cards dir",
            where=str(cards_dir(project_root)),
            why=["forge init ainda não criou snapshot, ou nome inválido em --card"],
        )

    all_violations: list[str] = []
    warnings_only: list[str] = []
    for card_yaml in cards:
        data = read_yaml_or_default(card_yaml, {}) or {}
        if not isinstance(data, dict):
            all_violations.append(f"{card_yaml.parent.name}: top-level not mapping")
            continue
        viols = core_validate(data, card_yaml.parent)
        for v in viols:
            label = f"{card_yaml.parent.name}: {v}"
            if "-WARN:" in v:
                warnings_only.append(label)
            else:
                all_violations.append(label)

    if all_violations:
        return result_fail(
            f"{len(all_violations)} violação(ões) em {len(cards)} card(s)",
            what_failed="; ".join(all_violations[:3])
            + (f" (+{len(all_violations)-3} more)" if len(all_violations) > 3 else ""),
            where="cards/*/card.yaml",
            why=[
                "docs/schemas/card.md §Validation define CARD-001..CARD-018.",
                "Loader rejeita cards inválidos — composer/resolver não funcionam.",
            ],
            paths=make_paths(
                "Editar o card.yaml e corrigir cada CARD-NNN listado",
                "Mensagens contêm o código + campo exato.",
                "Re-snapshot do canonical — `forge reconfigure → atualizar card`",
                "Se snapshot ficou stale vs canonical.",
                "Remover o card — `forge reconfigure → remover card`",
                "Se o card está deprecated ou broken.",
            ),
        )

    if warnings_only:
        return result_warn(
            f"{len(warnings_only)} warning(s) (CARD-*-WARN) em {len(cards)} card(s)",
            what_failed="; ".join(warnings_only[:3]),
            where="cards/*/card.yaml",
            why=["Warnings não bloqueiam — agentes sem extension-points formalizadas"],
        )

    return result_pass(f"{len(cards)} card(s) com schema válido (CARD-001..018)")


def _extra_args(parser: Any) -> None:
    parser.add_argument("--card", required=False, help="Validate only this card name")


if __name__ == "__main__":
    sys.exit(run_cli(__doc__ or "", validate, extra_args=_extra_args))
