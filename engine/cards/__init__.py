"""Card system — loader, resolver, merger, snapshotter.

A *card* is the atomic composition unit of feature-forge. This subpackage owns:

- `loader`       — read `card.yaml` from disk and validate against CARD-001..018.
- `resolver`     — check requires/conflicts, topo-sort, surface errors/warnings.
- `merger`       — collect contributions (templates, validators, agent-prompts,
                   hooks, config-defaults) from active cards and render them
                   deterministically.
- `snapshotter`  — copy cards from the canonical `~/Documents/feature-forge/cards/`
                   into a project's `.claude/cards/` and hash them for integrity.

See `docs/schemas/card.md` for the full schema and resolver behaviour.
"""

from __future__ import annotations


class CardError(Exception):
    """Raised for any human-fixable problem in the card subsystem.

    Used by loader (parse/validation errors), resolver (missing deps, conflicts,
    cycles), merger (unknown merge mode, duplicate keys) and snapshotter
    (integrity mismatch). Carries a single message — callers decide how to
    surface it (renderer, CLI exit code, etc.).
    """


class CardConflictError(CardError):
    """Raised when a canon card name collides with a local overlay card name.

    Approach A (cascade simples): conflito é hard fail. Resolução exige
    renomear o card local ou abrir ADR para promoção ao canon. NÃO há
    merge silencioso, NÃO há override.
    """


__all__ = ["CardError", "CardConflictError"]
