"""Card resolver — dependency + conflict + topological sort.

Implements the Step 1–3 algorithm from `docs/schemas/card.md §Resolver behavior`:

1. Dependency check — every `requires:` label must be provided by another
   active card OR by `user_provided_capabilities` (latentes such as
   `android-platform`, `ios-platform`, `swift-language`).
2. Conflict check — for a card name or label in `conflicts-with`, no other
   active card may match. Singular labels (one provider per project) raise
   a conflict when two cards both provide them.
3. Topological sort — deterministic order by dependency, alphabetical tiebreak.

The resolver returns a `ResolverResult`. Errors block install; warnings are
informational (e.g. duplicate config-defaults — those live in the merger, not
here).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .loader import CardManifest, known_singular_labels


@dataclass
class ResolverResult:
    """Outcome of `resolve()`. `activated` is empty when `errors` is non-empty."""

    activated: list[CardManifest] = field(default_factory=list)
    resolved_capabilities: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def resolve(
    candidate_cards: list[CardManifest],
    *,
    user_provided_capabilities: list[str] | None = None,
) -> ResolverResult:
    """Resolve a candidate set of cards.

    `user_provided_capabilities` covers latentes (`android-platform`,
    `ios-platform`, `swift-language`) — these are provided by the environment,
    not by any card.
    """
    user_caps = set(user_provided_capabilities or [])
    result = ResolverResult()

    # Sorted-by-name for deterministic error reporting + tiebreak.
    cards = sorted(candidate_cards, key=lambda c: c.name)

    # Build the capability index: label → list of providing card names.
    providers: dict[str, list[str]] = {}
    name_to_card: dict[str, CardManifest] = {c.name: c for c in cards}
    for card in cards:
        for label in card.provides:
            providers.setdefault(label, []).append(card.name)
    for cap in user_caps:
        providers.setdefault(cap, []).append("<environment>")

    # ── Step 1 — Dependency check ────────────────────────────────────────────
    for card in cards:
        for need in card.requires:
            if need not in providers:
                result.errors.append(
                    f"DEP-MISSING: card {card.name!r} requires {need!r} but no "
                    f"active card provides it (and it is not a user-provided "
                    f"capability)."
                )

    # ── Step 2 — Singular-label conflict ─────────────────────────────────────
    singular_labels = known_singular_labels()
    for label, plist in sorted(providers.items()):
        if label not in singular_labels:
            continue
        card_providers = [n for n in plist if n != "<environment>"]
        if len(card_providers) > 1:
            result.errors.append(
                f"CONFLICT-SINGULAR: capability {label!r} is singular but "
                f"provided by multiple cards: {sorted(card_providers)}"
            )

    # ── Step 2b — `conflicts-with` declarations ──────────────────────────────
    for card in cards:
        for entry in card.conflicts_with:
            # An entry can be a capability label or a specific card name.
            if entry in name_to_card and entry != card.name:
                result.errors.append(
                    f"CONFLICT-NAME: card {card.name!r} declares conflict with "
                    f"{entry!r} which is also active."
                )
                continue
            # Label form — error if any OTHER card provides it.
            conflicting_cards = [
                n for n in providers.get(entry, []) if n not in (card.name, "<environment>")
            ]
            # Self-declared `conflicts-with: [<own provide>]` is the canonical
            # idiom for "singular" — silent if no other provider exists.
            if entry in card.provides and not conflicting_cards:
                continue
            if conflicting_cards:
                result.errors.append(
                    f"CONFLICT-LABEL: card {card.name!r} declares conflict with "
                    f"capability {entry!r}, also provided by: {sorted(conflicting_cards)}"
                )

    if result.errors:
        return result

    # ── Step 3 — Topological sort ────────────────────────────────────────────
    try:
        result.activated = topo_sort(cards)
    except CycleError as exc:
        result.errors.append(f"CYCLE: {exc}")
        return result

    # ── Resolved capabilities map (label → first providing card name) ────────
    for label, plist in providers.items():
        card_providers = sorted(n for n in plist if n != "<environment>")
        if card_providers:
            result.resolved_capabilities[label] = card_providers[0]
        else:
            result.resolved_capabilities[label] = "<environment>"

    return result


class CycleError(RuntimeError):
    """Internal — raised by topo_sort when a dependency cycle is detected."""


def topo_sort(cards: list[CardManifest]) -> list[CardManifest]:
    """Topological sort by `requires`/`provides`.

    Deterministic: ties are broken alphabetically by card name. Cards whose
    `requires` are only satisfied by user-provided capabilities (latentes)
    sort first along with truly leaf cards.

    Raises `CycleError` if a cycle is detected.
    """
    name_to_card = {c.name: c for c in cards}

    # provider_of[label] = card_name (first card that provides; ties: alphabetical)
    provider_of: dict[str, str] = {}
    for card in sorted(cards, key=lambda c: c.name):
        for label in card.provides:
            provider_of.setdefault(label, card.name)

    # Build adjacency: card.name → set of card names it depends on (only on
    # capabilities provided by another card in the set — external/latent
    # requires are dropped since they cannot create a cycle here).
    deps: dict[str, set[str]] = {c.name: set() for c in cards}
    for card in cards:
        for need in card.requires:
            provider = provider_of.get(need)
            if provider and provider != card.name:
                deps[card.name].add(provider)

    # Kahn's algorithm with alphabetical tiebreak.
    in_degree: dict[str, int] = {name: len(d) for name, d in deps.items()}
    reverse: dict[str, set[str]] = {c.name: set() for c in cards}
    for child, parents in deps.items():
        for p in parents:
            reverse[p].add(child)

    ready = sorted([name for name, deg in in_degree.items() if deg == 0])
    out: list[CardManifest] = []

    while ready:
        # Always pop the alphabetically smallest ready node.
        current = ready.pop(0)
        out.append(name_to_card[current])
        for child in sorted(reverse[current]):
            in_degree[child] -= 1
            if in_degree[child] == 0:
                # Insert keeping `ready` sorted.
                _insert_sorted(ready, child)

    if len(out) != len(cards):
        remaining = sorted(set(name_to_card) - {c.name for c in out})
        raise CycleError(
            f"dependency cycle detected involving cards: {remaining}"
        )
    return out


def _insert_sorted(seq: list[str], item: str) -> None:
    """Insertion sort step — keeps `seq` alphabetically sorted."""
    lo, hi = 0, len(seq)
    while lo < hi:
        mid = (lo + hi) // 2
        if seq[mid] < item:
            lo = mid + 1
        else:
            hi = mid
    seq.insert(lo, item)
