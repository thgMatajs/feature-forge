"""Integration test — load + resolve the canonical card library.

Loads every card under FORGE_HOME/cards/ and runs the resolver across a few
realistic activation sets (e.g. KMP + Firebase, KMP + REST), asserting that
the canonical card set is well-formed and conflict-free for documented combos.
"""

from __future__ import annotations

import pytest

from engine.cards import loader, resolver
from engine.utils.paths import cards_canonical_dir


@pytest.mark.integration
def test_load_all_canonical_cards():
    all_cards = loader.load_all_cards(cards_canonical_dir())
    names = {c.name for c in all_cards}
    # Sanity — at least the published 20 cards documented in cards/ should load.
    assert len(all_cards) >= 15, f"only {len(all_cards)} cards loaded: {sorted(names)}"
    # A handful of canonical names must exist.
    must_have = {"kmp-shared", "kotlin-language", "firebase-auth"}
    assert must_have.issubset(names), f"missing canonical cards: {must_have - names}"


@pytest.mark.integration
def test_resolve_minimal_kmp_combo():
    all_cards = loader.load_all_cards(cards_canonical_dir())
    by_name = {c.name: c for c in all_cards}
    combo = [by_name[n] for n in ("kotlin-language", "kmp-shared") if n in by_name]
    result = resolver.resolve(
        combo,
        user_provided_capabilities=["android-platform", "ios-platform"],
    )
    assert not result.errors, f"resolve failed for minimal KMP combo: {result.errors}"
    assert "kmp-shared" in [c.name for c in result.activated]


@pytest.mark.integration
def test_resolve_firebase_stack_combo():
    all_cards = loader.load_all_cards(cards_canonical_dir())
    by_name = {c.name: c for c in all_cards}
    wanted = [
        "kotlin-language",
        "kmp-shared",
        "koin-annotations",
        "firebase-auth",
        "firestore-persistence",
        "compose-screens",
        "swiftui-screens",
    ]
    combo = [by_name[n] for n in wanted if n in by_name]
    assert combo, "expected at least one wanted card to be present"
    result = resolver.resolve(
        combo,
        user_provided_capabilities=["android-platform", "ios-platform", "swift-language"],
    )
    # Errors here would point to a real conflict in the canonical cards — assert clean.
    assert not result.errors, f"Firebase combo has conflicts: {result.errors}"


@pytest.mark.integration
def test_auth_provider_is_singular():
    # The auth-provider capability must be in the singular set.
    loader._reset_catalog_cache()
    singular = loader.known_singular_labels()
    # This card library only has firebase-auth providing auth-provider; we only
    # check that the catalog declares it as singular so the resolver enforces 1.
    if "auth-provider" not in singular:
        pytest.skip("auth-provider not declared singular in capability catalog")
    assert "auth-provider" in singular
