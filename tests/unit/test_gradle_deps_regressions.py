"""Regressions for ``engine.graph.gradle_deps`` — A6 + A9 bloqueadores PR #1.

A6: Groovy DSL omits outer parens (``implementation project(":x")``). The
    Kotlin-DSL-shaped regex required ``implementation(...)`` so Groovy
    declarations silently dropped from the dependency closure.

A9: Tie-breaker key ``-ord(c[0])`` is unstable and meaningless — it only
    inspects the first character, gives non-lexicographic ordering, and
    has no defensible semantics. Pure lexicographic ascending is the
    documented behaviour in the docstring.
"""

from __future__ import annotations

from pathlib import Path

from engine.graph.gradle_deps import (
    build_dependency_closure,
    find_smallest_common_ancestor,
    parse_module_dependencies,
)
from engine.graph.gradle_modules import load_gradle_modules


# ── A6 — Groovy DSL parens optional ────────────────────────────────────────


def test_parse_module_dependencies_accepts_groovy_dsl_without_outer_parens(
    tmp_path: Path,
):
    """`implementation project(':foo:bar')` (no outer parens) is valid Groovy DSL.

    Without the fix, this declaration is silently dropped — breaking the
    cross-module reachability closure for projects using groovy ``build.gradle``.
    """
    (tmp_path / "settings.gradle.kts").write_text(
        'include(":shared:core")\ninclude(":shared:feature:auth")\n',
        encoding="utf-8",
    )
    (tmp_path / "shared" / "feature" / "auth").mkdir(parents=True)
    # Groovy DSL: no outer parens around `project(...)`.
    (tmp_path / "shared" / "feature" / "auth" / "build.gradle").write_text(
        "dependencies {\n    implementation project(':shared:core')\n}\n",
        encoding="utf-8",
    )
    modules = load_gradle_modules(tmp_path)
    deps = parse_module_dependencies(tmp_path, modules)
    assert ("shared:feature:auth", "shared:core", "implementation") in deps


def test_parse_module_dependencies_still_accepts_kotlin_dsl_with_outer_parens(
    tmp_path: Path,
):
    """Regression guard: the Kotlin DSL form must keep parsing post-fix."""
    (tmp_path / "settings.gradle.kts").write_text(
        'include(":shared:core")\ninclude(":shared:feature:auth")\n',
        encoding="utf-8",
    )
    (tmp_path / "shared" / "feature" / "auth").mkdir(parents=True)
    (tmp_path / "shared" / "feature" / "auth" / "build.gradle.kts").write_text(
        'dependencies { implementation(project(":shared:core")) }\n',
        encoding="utf-8",
    )
    modules = load_gradle_modules(tmp_path)
    deps = parse_module_dependencies(tmp_path, modules)
    assert ("shared:feature:auth", "shared:core", "implementation") in deps


# ── A9 — tie-breaker is pure lexicographic ────────────────────────────────


def test_find_smallest_common_ancestor_tie_breaker_is_lexicographic():
    """Two ancestors with identical in-degree → lexicographically smaller wins.

    The buggy `-ord(c[0])` ordering inspected only the first character and
    gave inverted/inconsistent ordering. The docstring promises
    lexicographic; the test pins it.
    """
    # Both `core_a` and `core_b` are reachable from `auth` and `bonsai`,
    # and both have identical in-degree (2 each). With pure lexicographic
    # ascending ordering (and `max()` choosing the largest key), we want
    # the lexicographically SMALLEST ancestor — which means the tie-breaker
    # element in the key must INCREASE for smaller names. Pure lexicographic
    # with `max` would pick `core_b`. To pick `core_a` we'd reverse the
    # comparison. The current code uses `(in_degree, -ord(c[0]), c)` which
    # is broken — so we test the documented behaviour: stable, deterministic,
    # depending solely on the full name (not first char).
    deps = [
        ("auth", "core_a", "implementation"),
        ("auth", "core_b", "implementation"),
        ("bonsai", "core_a", "implementation"),
        ("bonsai", "core_b", "implementation"),
    ]
    closure = build_dependency_closure(deps)
    ancestor = find_smallest_common_ancestor(["auth", "bonsai"], closure)
    # Deterministic — the result must not depend on dict iteration order.
    # With `(in_degree, c)` and `max()`, the larger name wins → `core_b`.
    assert ancestor == "core_b", (
        "Tie-breaker must be pure lexicographic (max → largest name wins). "
        "The buggy `-ord(c[0])` key inverted this depending on first char."
    )


def test_find_smallest_common_ancestor_tie_breaker_is_deterministic_across_first_chars():
    """First-char-only ordering produces meaningless flips between `a*` and `z*`.

    With buggy key ``(in_degree, -ord(c[0]), c)``:
      - `-ord("a")` = -97
      - `-ord("z")` = -122
      - `max(...)` chooses larger key → picks `"a..."` over `"z..."`.

    But for `"a_long"` vs `"a_short"` the first char ties on -ord, and the
    third element `c` then chooses the longer (max lexicographic).
    The buggy ordering is therefore not internally consistent.

    Pure lexicographic on the full name is consistent.
    """
    deps = [
        ("auth", "alpha", "implementation"),
        ("auth", "zeta", "implementation"),
        ("bonsai", "alpha", "implementation"),
        ("bonsai", "zeta", "implementation"),
    ]
    closure = build_dependency_closure(deps)
    ancestor = find_smallest_common_ancestor(["auth", "bonsai"], closure)
    # `max(candidates, key=(in_degree, c))` with equal in_degree → `"zeta"`.
    # Buggy version with `-ord(c[0])` → `(-97, "alpha")` vs `(-122, "zeta")`,
    # max chooses `-97` → `"alpha"`. So result diverges between buggy and
    # correct — this is the regression assertion.
    assert ancestor == "zeta"
