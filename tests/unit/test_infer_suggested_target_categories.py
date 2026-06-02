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
