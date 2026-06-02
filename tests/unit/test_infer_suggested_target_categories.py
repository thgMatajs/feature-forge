"""Coverage — ``engine.graph.gradle_deps.infer_suggested_target``.

Pins the exact path-format / hint-string output for each known category.
Tests are split into 5 functions, one per category, mirroring the
master-review list:

  - duplicate-within-module
  - duplicate-cross-module
  - near-duplicate
  - kmp-migration-candidate
  - redundant-platform-specific

This is the integration point where ``forge graph`` query results get
turned into actionable "where should this live" hints — drift here
silently breaks the intake stubs.
"""

from __future__ import annotations

from engine.graph.gradle_deps import infer_suggested_target


def test_infer_target_duplicate_within_module() -> None:
    """Single-module dup → suggest a util/ path inside that module's main/kotlin."""
    result = infer_suggested_target(
        category="duplicate-within-module",
        modules_in_group=["app:android"],
        closure={},
        gradle_modules={"app/android": "app:android"},
    )
    assert result == "app/android/src/main/kotlin/.../util/"


def test_infer_target_duplicate_cross_module_with_shared_ancestor() -> None:
    """Cross-module dup with shared:core registered → commonMain path under shared:core.

    No closure is provided, so ``find_smallest_common_ancestor`` returns
    ``None`` and ``_static_cross_module_fallback`` kicks in: it sees a
    ``shared:*`` module in the group, ``shared:core`` is registered, so
    the ancestor resolves to ``shared:core``. Because the ancestor starts
    with ``shared``, the path is the ``commonMain`` variant.
    """
    result = infer_suggested_target(
        category="duplicate-cross-module",
        modules_in_group=["app:android", "shared:foo"],
        closure={},  # forces fallback path
        # ``load_gradle_modules`` returns ``{dir_path: gradle_module_name}``.
        # The fallback inspects ``set(gradle_modules.values())`` for
        # ``shared:core`` — so registered gradle NAMES go on the value side.
        gradle_modules={
            "app/android": "app:android",
            "shared/foo": "shared:foo",
            "shared/core": "shared:core",
        },
    )
    assert result == "shared/core/src/commonMain/kotlin/.../util/"


def test_infer_target_near_duplicate() -> None:
    """Near-dup never auto-suggests a path — bodies diverged, manual review."""
    result = infer_suggested_target(
        category="near-duplicate",
        modules_in_group=["app:android", "shared:foo"],
        closure={},
        gradle_modules={},
    )
    assert result == "manual review — bodies divergem"


def test_infer_target_kmp_migration_candidate() -> None:
    """KMP candidate → fixed hint, not a path. Swift consumer should SKIE-call shared."""
    result = infer_suggested_target(
        category="kmp-migration-candidate",
        modules_in_group=["shared:core"],
        closure={},
        gradle_modules={},
    )
    assert result == "replace Swift extension with SKIE call to shared"


def test_infer_target_redundant_platform_specific() -> None:
    """Redundant platform copy → keep the shared variant, remove the rest."""
    result = infer_suggested_target(
        category="redundant-platform-specific",
        modules_in_group=["shared:foo", "app:android"],
        closure={},
        gradle_modules={},
    )
    assert result == "keep: shared:foo · remove: app:android"
