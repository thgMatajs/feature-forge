#!/usr/bin/env python3
"""validate_capability_labels.py — Capability label catalog enforcement.

For every `cards/{name}/card.yaml` (or the snapshot under `.claude/cards/`),
validates that every label in `provides` / `requires` / `conflicts-with` is
present in the **effective catalog** (canon ∪ local overlay).

- Canon: `docs/schemas/capability-labels.md` (source-of-truth)
- Overlay: `.claude/inventory/capability-labels.local.yaml` (project-local additions)

Behavior:
- Out-of-catalog labels → fail
- Reserved labels (still planned, canon-only) → warn
- Overlay malformed / forbidden keys / collision with canon → fail (CatalogOverlayError)

Schema source: docs/schemas/capability-labels.md.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from _common import (
    CatalogOverlayError,
    load_catalog,
    make_paths,
    result_fail,
    result_pass,
    result_warn,
    run_cli,
)

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.utils.paths import cards_canonical_dir, cards_dir  # noqa: E402
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


def validate(project_root: Path, **kwargs: Any) -> dict[str, Any]:
    """Validate every card's capability-label usage against canon ∪ local catalog."""
    cards = _collect_cards(project_root)
    if not cards:
        return result_warn(
            "nenhum card.yaml encontrado pra validar",
            what_failed="empty cards dir",
            where=str(cards_dir(project_root)),
            why=["forge init ainda não rodou, ou snapshot vazio"],
        )

    try:
        catalog = load_catalog(project_root)
    except CatalogOverlayError as exc:
        return result_fail(
            "capability-labels.local.yaml inválido",
            what_failed=str(exc),
            where=".claude/inventory/capability-labels.local.yaml",
            why=[
                "Overlay tem guards: sem `overrides`, sem `reserved-promotions`,",
                "sem colisão com canon ativo, sem promoção de reservada.",
            ],
            paths=make_paths(
                "Corrigir o YAML local — remover chaves proibidas",
                "Validator rejeita overlay que tenta redefinir canon.",
                "Renomear label local para evitar colisão",
                "Active set canon tem precedência (Approach A).",
                "Abrir ADR pra promoção ao canon",
                "Promoção exige revisita do catálogo, não overlay.",
            ),
        )

    active = catalog.active
    reserved = catalog.reserved

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
                if label not in active:
                    failures.append(
                        f"{card_yaml.parent.name}.{block_name}: {label!r} out-of-catalog"
                    )
                elif label in reserved:
                    reserved_hits.append(
                        f"{card_yaml.parent.name}.{block_name}: {label!r} (reserved)"
                    )

    if failures:
        return result_fail(
            f"{len(failures)} label(s) out-of-catalog em {cards_checked} card(s)",
            what_failed="; ".join(failures[:3])
            + (f" (+{len(failures)-3} more)" if len(failures) > 3 else ""),
            where="cards/*/card.yaml",
            why=[
                "capability-labels.md é source-of-truth canon (CARD-006/CARD-007).",
                "Overlay pode adicionar labels via capability-labels.local.yaml.",
                "Labels fora do catálogo efetivo quebram resolução de cards.",
            ],
            paths=make_paths(
                "Adicionar a label ao docs/schemas/capability-labels.md (PR canon)",
                "Catalog evolve via 1-file change; veja seção Reserved.",
                "Adicionar a label ao .claude/inventory/capability-labels.local.yaml",
                "Overlay aceita additions com schema enxuto (`added: [...]`).",
                "Editar o card.yaml e usar label canônica equivalente",
                "Costuma haver sinônimo no catalog.",
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
        f"{cards_checked} card(s) com labels todas no catálogo efetivo (canon ∪ local)"
    )


def _extra_args(parser: Any) -> None:
    parser.add_argument("--card", required=False, help="Validate only this card name")


if __name__ == "__main__":
    sys.exit(run_cli(__doc__ or "", validate, extra_args=_extra_args))
