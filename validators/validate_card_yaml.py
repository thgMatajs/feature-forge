#!/usr/bin/env python3
"""validate_card_yaml.py — Thin wrapper over engine.cards.loader.validate_card_yaml.

Validates one (--card NAME) or all card.yaml files under either the project's
snapshot (`.claude/cards/`) — including the local overlay
`.claude/forge/cards/local/` (Task 0.8 — v1.3 sub-namespace) —
or the canonical library (`cards/`) as fallback.
Surfaces every CARD-001..CARD-019 violation.

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
from engine.utils.paths import (  # noqa: E402
    cards_canonical_dir,
    cards_dir,
    forge_cards_local_dir,
)
from engine.utils.yaml_io import YamlIOError, read_yaml_or_default  # noqa: E402


def _collect_cards(
    project_root: Path, only: str | None = None
) -> list[tuple[Path, str]]:
    """Return list of (card_yaml_path, origin) where origin ∈ {"canon", "local"}.

    Cascade:
      - canon snapshot: `<project>/.claude/cards/<name>/card.yaml`
      - local overlay: `<project>/.claude/forge/cards/local/<name>/card.yaml`
        (Task 0.8 — v1.3 sub-namespace; antes vivia em `.claude/cards/local/`)
      - fallback: canonical library `<forge_home>/cards/<name>/card.yaml` quando snapshot vazio
    """
    candidates: list[tuple[Path, str]] = []
    snapshot = cards_dir(project_root)
    if snapshot.is_dir():
        for entry in snapshot.glob("*/card.yaml"):
            # Pula a subpasta `local/` legacy — não deveria mais existir
            # após migração, mas continuamos defensivos.
            if entry.parent.parent.name == "local":
                continue
            if entry.parent.name == "local":
                continue
            candidates.append((entry, "canon"))
    # Task 0.8: local overlay agora vive em .claude/forge/cards/local/.
    local_root = forge_cards_local_dir(project_root)
    if local_root.is_dir():
        for entry in local_root.glob("*/card.yaml"):
            candidates.append((entry, "local"))
    if not candidates:
        canonical = cards_canonical_dir()
        if canonical.is_dir():
            for entry in canonical.glob("*/card.yaml"):
                candidates.append((entry, "canon"))
    if only:
        candidates = [(p, o) for p, o in candidates if p.parent.name == only]
    return sorted(candidates, key=lambda t: (t[1], str(t[0])))


def validate(project_root: Path, **kwargs: Any) -> dict[str, Any]:
    """Run engine.cards.loader.validate_card_yaml against every card.

    Cross-checks adicionados:
      - Colisão canon ∩ local (hard fail, dispara antes do schema check)
      - Mensagens carregam contexto `[canon]` ou `[local]` por path
    """
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

    # Cross-check: colisão de nome canon ∩ local (Approach A — hard fail).
    canon_names = {p.parent.name for p, o in cards if o == "canon"}
    local_names = {p.parent.name for p, o in cards if o == "local"}
    collisions = sorted(canon_names & local_names)
    if collisions:
        return result_fail(
            f"colisão de nome canon×local em {len(collisions)} card(s)",
            what_failed=", ".join(collisions),
            where=".claude/cards/<name>/ + .claude/forge/cards/local/<name>/",
            why=[
                "Approach A: card local não pode ter o mesmo nome de canon ativo.",
                "Sem merge silencioso, sem override — escolha consciente exigida.",
            ],
            paths=make_paths(
                "Renomear o card local (`forge reconfigure → card-local → remover` + criar com nome novo)",
                "Mais simples — local pode ter nome qualquer fora do canon.",
                "Abrir ADR pra promoção do card local ao canon",
                "Quando a semântica está madura pra entrar no catálogo oficial.",
                "Remover o canon e manter só local (revisita decisão)",
                "Raríssimo — exige revisita do catálogo canon.",
            ),
        )

    all_violations: list[str] = []
    warnings_only: list[str] = []
    for card_yaml, origin in cards:
        # C13: read_yaml_or_default + downstream parse podem disparar
        # YamlIOError ou erros de I/O. Antes, exceptions vazavam pra cima
        # e abortavam a cascade no primeiro card malformado, perdendo
        # contexto dos demais. Wrap → coleta como failure por card.
        try:
            data = read_yaml_or_default(card_yaml, {}) or {}
        except (YamlIOError, OSError, UnicodeDecodeError) as exc:
            all_violations.append(
                f"[{origin}] {card_yaml.parent.name}: "
                f"failed to parse YAML ({exc})"
            )
            continue
        if not isinstance(data, dict):
            all_violations.append(
                f"[{origin}] {card_yaml.parent.name}: top-level not mapping"
            )
            continue
        viols = core_validate(data, card_yaml.parent)
        for v in viols:
            label = f"[{origin}] {card_yaml.parent.name}: {v}"
            if "-WARN:" in v:
                warnings_only.append(label)
            else:
                all_violations.append(label)

    if all_violations:
        return result_fail(
            f"{len(all_violations)} violação(ões) em {len(cards)} card(s)",
            what_failed="; ".join(all_violations[:3])
            + (f" (+{len(all_violations)-3} more)" if len(all_violations) > 3 else ""),
            where="cards/*/card.yaml + .claude/forge/cards/local/*/card.yaml",
            why=[
                "docs/schemas/card.md §Validation define CARD-001..CARD-019.",
                "Loader rejeita cards inválidos — composer/resolver não funcionam.",
                "Contexto `[canon]` ou `[local]` identifica camada do erro.",
            ],
            paths=make_paths(
                "Editar o card.yaml e corrigir cada CARD-NNN listado",
                "Mensagens contêm o código + campo exato + camada.",
                "Re-snapshot do canonical — `forge reconfigure → atualizar card`",
                "Quando o erro está em camada canon (origem oficial).",
                "Remover o card local — `forge reconfigure → card-local → remover`",
                "Quando o erro está só no overlay local.",
            ),
        )

    if warnings_only:
        return result_warn(
            f"{len(warnings_only)} warning(s) em {len(cards)} card(s)",
            what_failed="; ".join(warnings_only[:3]),
            where="cards/*/card.yaml + .claude/forge/cards/local/*/card.yaml",
            why=["Warnings não bloqueiam — agentes sem extension-points formalizadas"],
        )

    return result_pass(
        f"{len(cards)} card(s) com schema válido (canon + local, CARD-001..019)"
    )


def _extra_args(parser: Any) -> None:
    parser.add_argument("--card", required=False, help="Validate only this card name")


if __name__ == "__main__":
    sys.exit(run_cli(__doc__ or "", validate, extra_args=_extra_args))
