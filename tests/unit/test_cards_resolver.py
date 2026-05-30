"""Unit tests — engine.cards.resolver.

Drives `resolve()` with synthetic CardManifest objects to validate:
- happy path returns topo-sorted activated list
- missing dependency surfaces DEP-MISSING
- singular-label conflict surfaces CONFLICT-SINGULAR
- explicit `conflicts-with` triggers CONFLICT-NAME
- topo_sort is deterministic and breaks ties alphabetically
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.cards.loader import CardManifest
from engine.cards import resolver


def _card(
    name: str,
    *,
    provides: list[str] | None = None,
    requires: list[str] | None = None,
    conflicts: list[str] | None = None,
) -> CardManifest:
    return CardManifest(
        name=name,
        version="1.0.0",
        schema_version=1,
        description="",
        category="kmp",
        maturity="stable",
        provides=provides or [],
        requires=requires or [],
        conflicts_with=conflicts or [],
        source_path=Path("."),
    )


def test_resolve_happy_path_no_conflicts():
    cards = [
        _card("language", provides=["kotlin"]),
        _card("shared", provides=["kotlin-multiplatform"], requires=["kotlin"]),
    ]
    result = resolver.resolve(cards)
    assert not result.errors
    names = [c.name for c in result.activated]
    # 'language' must come before 'shared' (provides kotlin).
    assert names.index("language") < names.index("shared")


def test_resolve_missing_dependency():
    cards = [_card("shared", requires=["kotlin"])]
    result = resolver.resolve(cards)
    assert any("DEP-MISSING" in e for e in result.errors)


def test_resolve_user_provided_capability_satisfies_requirement():
    cards = [_card("ios-ui", requires=["ios-platform"])]
    result = resolver.resolve(cards, user_provided_capabilities=["ios-platform"])
    assert not result.errors
    assert result.resolved_capabilities["ios-platform"] == "<environment>"


def test_resolve_singular_capability_conflict(monkeypatch):
    # Force a known singular label so the test does not depend on the live catalog.
    monkeypatch.setattr(
        resolver,
        "known_singular_labels",
        lambda: frozenset({"auth-provider"}),
    )
    cards = [
        _card("firebase-auth", provides=["auth-provider"]),
        _card("custom-auth", provides=["auth-provider"]),
    ]
    result = resolver.resolve(cards)
    assert any("CONFLICT-SINGULAR" in e for e in result.errors)


def test_resolve_conflicts_with_name():
    cards = [
        _card("a", conflicts=["b"]),
        _card("b"),
    ]
    result = resolver.resolve(cards)
    assert any("CONFLICT-NAME" in e for e in result.errors)


def test_resolve_conflicts_with_label():
    cards = [
        _card("alpha", provides=["x"], conflicts=["x"]),  # self conflict on own label — silent
        _card("beta", provides=["x"]),
    ]
    result = resolver.resolve(cards)
    assert any("CONFLICT-LABEL" in e for e in result.errors)


def test_topo_sort_alphabetical_tiebreak():
    cards = [
        _card("zeta"),
        _card("alpha"),
        _card("middle"),
    ]
    ordered = resolver.topo_sort(cards)
    # All independent — sort by name.
    assert [c.name for c in ordered] == ["alpha", "middle", "zeta"]


def test_topo_sort_detects_cycle():
    a = _card("a", provides=["cap-a"], requires=["cap-b"])
    b = _card("b", provides=["cap-b"], requires=["cap-a"])
    with pytest.raises(resolver.CycleError):
        resolver.topo_sort([a, b])


def test_resolve_resolved_capabilities_first_provider_wins():
    cards = [
        _card("alpha", provides=["shared-cap"]),
        _card("beta", provides=["shared-cap"]),
    ]
    # Force no singular conflict by stubbing the catalog.
    import engine.cards.resolver as r

    original = r.known_singular_labels
    r.known_singular_labels = lambda: frozenset()
    try:
        result = resolver.resolve(cards)
        assert "shared-cap" in result.resolved_capabilities
        # Alphabetical winner.
        assert result.resolved_capabilities["shared-cap"] == "alpha"
    finally:
        r.known_singular_labels = original
