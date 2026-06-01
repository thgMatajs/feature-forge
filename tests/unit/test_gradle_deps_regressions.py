"""Regressions for ``engine.graph.gradle_deps`` — A6 + A9 + CR-02 + MD-01.

A6: Groovy DSL omits outer parens (``implementation project(":x")``). The
    Kotlin-DSL-shaped regex required ``implementation(...)`` so Groovy
    declarations silently dropped from the dependency closure.

A9 / CR-02: Tie-breaker key was ``-ord(c[0])`` then ``(in_degree, c)`` with
    ``max()`` — both meaningless or inverted. Function is named
    ``find_smallest_common_ancestor`` and docstring promises "smallest";
    the only semantically defensible tie-breaker is the lexicographically
    SMALLEST name. Fix uses ``min(..., key=(-in_degree, c))``.

MD-01: Groovy DSL frequently appears with a trailing closure
    (``implementation project(':x') { transitive = false }``). The closure
    must not block the regex from matching the dependency.
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
    """Two ancestors with identical in-degree → lexicographically SMALLEST wins.

    Function name ("smallest") + docstring ("Tie-breaker: lexicographically
    smallest name wins") pin the semantics. The fix uses
    ``min(candidates, key=(-in_degree, c))`` so highest in-degree wins
    and ties go to the lex-smaller name.
    """
    deps = [
        ("auth", "core_a", "implementation"),
        ("auth", "core_b", "implementation"),
        ("bonsai", "core_a", "implementation"),
        ("bonsai", "core_b", "implementation"),
    ]
    closure = build_dependency_closure(deps)
    ancestor = find_smallest_common_ancestor(["auth", "bonsai"], closure)
    assert ancestor == "core_a", (
        "Tie-breaker must pick the lexicographically SMALLEST name when "
        "in_degree ties — function is literally named "
        "`find_smallest_common_ancestor`."
    )


def test_find_smallest_common_ancestor_tie_breaker_is_deterministic_across_first_chars():
    """Lex-smallest tie-break works regardless of first-character distance.

    Both ``alpha`` and ``zeta`` have identical in-degree here; the fix
    must pick ``alpha`` (lex-smallest) deterministically.
    """
    deps = [
        ("auth", "alpha", "implementation"),
        ("auth", "zeta", "implementation"),
        ("bonsai", "alpha", "implementation"),
        ("bonsai", "zeta", "implementation"),
    ]
    closure = build_dependency_closure(deps)
    ancestor = find_smallest_common_ancestor(["auth", "bonsai"], closure)
    assert ancestor == "alpha"


# ── MD-01 — Groovy DSL with trailing closure ──────────────────────────────


def test_parse_module_dependencies_accepts_groovy_dsl_with_trailing_closure(
    tmp_path: Path,
):
    """``implementation project(':x') { transitive = false }`` must still parse.

    Real-world Groovy ``build.gradle`` files frequently chain a configuration
    closure onto the ``project(...)`` call. The regex must tolerate optional
    whitespace + closure block after the ``project(...)`` call.
    """
    (tmp_path / "settings.gradle.kts").write_text(
        'include(":shared:core")\ninclude(":shared:feature:auth")\n',
        encoding="utf-8",
    )
    (tmp_path / "shared" / "feature" / "auth").mkdir(parents=True)
    (tmp_path / "shared" / "feature" / "auth" / "build.gradle").write_text(
        "dependencies {\n"
        "    implementation project(':shared:core') { transitive = false }\n"
        "}\n",
        encoding="utf-8",
    )
    modules = load_gradle_modules(tmp_path)
    deps = parse_module_dependencies(tmp_path, modules)
    assert ("shared:feature:auth", "shared:core", "implementation") in deps
