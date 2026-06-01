"""Gradle module dependency graph parsed from each module's ``build.gradle(.kts)``.

Used to:
- Populate the ``module_deps`` table during full rebuild.
- Compute transitive closure (which modules each module can reach).
- Infer "smallest common ancestor" target for cross-module duplications
  (e.g., a helper duplicated in ``:shared:feature:auth`` and
  ``:shared:feature:bonsai`` should land in ``:shared:core`` if both can
  reach it).

Pure regex parsing — covers the common DSL forms, gracefully degrades on
exotic patterns by returning an empty dict (suggested_target falls back to
the static heuristic).
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Iterable, Optional

from engine.graph.gradle_modules import module_dir

# Common dependency scopes we care about for the closure. `implementation` /
# `api` are the load-bearing ones; the rest are kept so doctor / debug can show
# the full picture without us re-parsing.
_DEP_SCOPES = (
    "implementation",
    "api",
    "compileOnly",
    "runtimeOnly",
    "testImplementation",
    "androidTestImplementation",
    "kapt",
    "ksp",
)

_RE_PROJECT_DEP = re.compile(
    r"""
    \b(?P<scope>%s)
    (?:\s*\(\s*|\s+)              # Kotlin DSL `scope(` OR Groovy DSL `scope `
    project\s*\(\s*               # project() wrapper
    ['"]:(?P<target>[\w:\-]+)['"]  # ":target:module"
    \s*\)
    \s*\)?                        # Kotlin DSL closes the outer call; Groovy omits it
    """ % "|".join(_DEP_SCOPES),
    re.VERBOSE | re.MULTILINE,
)


def parse_module_dependencies(
    project_root: Path,
    gradle_modules: dict[str, str],
) -> list[tuple[str, str, str]]:
    """Walk every module's ``build.gradle(.kts)`` and extract project deps.

    Returns ``[(from_module, to_module, scope), ...]`` deduped. Missing or
    unreadable build files are silently skipped — better partial info than
    blowing up an init that's otherwise green.
    """
    seen: set[tuple[str, str, str]] = set()
    for dir_path, gradle_name in gradle_modules.items():
        for filename in ("build.gradle.kts", "build.gradle"):
            build_file = project_root / dir_path / filename
            if not build_file.exists():
                continue
            try:
                text = build_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for match in _RE_PROJECT_DEP.finditer(text):
                scope = match.group("scope")
                target = match.group("target")
                seen.add((gradle_name, target, scope))
    return sorted(seen)


def persist_module_dependencies(
    conn: sqlite3.Connection,
    deps: Iterable[tuple[str, str, str]],
) -> int:
    """Insert dependency rows into ``module_deps``. Returns the count persisted."""
    rows = list(deps)
    if not rows:
        return 0
    conn.executemany(
        "INSERT OR IGNORE INTO module_deps(from_module, to_module, scope) VALUES(?, ?, ?)",
        rows,
    )
    return len(rows)


def build_dependency_closure(
    deps: Iterable[tuple[str, str, str]],
) -> dict[str, frozenset[str]]:
    """Compute transitive reachability per module.

    ``closure[m]`` = every module ``m`` can reach via implementation/api/etc.,
    including ``m`` itself. Scope is ignored on purpose — for the smallest
    common ancestor heuristic we treat every project dependency as a usable
    edge regardless of whether it's test-only.
    """
    adj: dict[str, set[str]] = {}
    nodes: set[str] = set()
    for from_module, to_module, _scope in deps:
        adj.setdefault(from_module, set()).add(to_module)
        nodes.add(from_module)
        nodes.add(to_module)

    closure: dict[str, set[str]] = {}
    for start in nodes:
        visited: set[str] = {start}
        stack: list[str] = list(adj.get(start, set()))
        while stack:
            node = stack.pop()
            if node in visited:
                continue
            visited.add(node)
            stack.extend(adj.get(node, set()))
        closure[start] = visited

    return {k: frozenset(v) for k, v in closure.items()}


def find_smallest_common_ancestor(
    modules_in_group: list[str],
    closure: dict[str, frozenset[str]],
) -> Optional[str]:
    """Pick the module that all ``modules_in_group`` can depend on.

    Returns ``None`` when no shared ancestor exists in the graph — caller
    should fall back to a static heuristic (e.g., ``:shared:core``).

    Selection rule when multiple ancestors qualify:
      1. Exclude modules in the input group themselves.
      2. Prefer modules with the highest in-degree (most "core-like").
      3. Tie-breaker: lexicographic order.
    """
    if not modules_in_group:
        return None

    reachable_per_module: list[frozenset[str]] = []
    for module in modules_in_group:
        reachable = closure.get(module, frozenset({module}))
        reachable_per_module.append(reachable | {module})

    if not reachable_per_module:
        return None

    candidates = set.intersection(*(set(r) for r in reachable_per_module))
    candidates -= set(modules_in_group)
    if not candidates:
        return None

    in_degree: dict[str, int] = {}
    for source, reach in closure.items():
        for target in reach:
            if target == source:
                continue
            in_degree[target] = in_degree.get(target, 0) + 1

    return max(candidates, key=lambda c: (in_degree.get(c, 0), c))


def infer_suggested_target(
    category: str,
    modules_in_group: list[str],
    closure: dict[str, frozenset[str]],
    gradle_modules: dict[str, str],
) -> str:
    """Heuristic suggestion for *where* a consolidated helper should live.

    Combines the dependency closure (when present) with static fallbacks. The
    returned string is a human-readable hint, not a literal path — apply
    handlers refine it when writing the intake stub.
    """
    if not modules_in_group:
        return "manual review"

    if category == "duplicate-within-module":
        module = modules_in_group[0]
        return f"{module_dir(module)}/src/main/kotlin/.../util/"

    if category == "duplicate-cross-module":
        ancestor = find_smallest_common_ancestor(modules_in_group, closure)
        if ancestor is None:
            ancestor = _static_cross_module_fallback(modules_in_group, gradle_modules)
        if ancestor.startswith("shared"):
            return f"{module_dir(ancestor)}/src/commonMain/kotlin/.../util/"
        return f"{module_dir(ancestor)}/src/main/kotlin/.../util/"

    if category == "redundant-platform-specific":
        shared_modules = [m for m in modules_in_group if m.startswith("shared")]
        keep = shared_modules[0] if shared_modules else modules_in_group[0]
        remove = [m for m in modules_in_group if m != keep]
        return f"keep: {keep} · remove: {', '.join(remove) if remove else '(none)'}"

    if category == "near-duplicate":
        return "manual review — bodies divergem"

    if category == "kmp-migration-candidate":
        return "replace Swift extension with SKIE call to shared"

    if category == "duplicate-ts-helper":
        module = modules_in_group[0]
        return f"{module_dir(module)}/util/"

    return "manual review"


def _static_cross_module_fallback(
    modules_in_group: list[str],
    gradle_modules: dict[str, str],
) -> str:
    """Fallback when the dependency closure is empty or has no common ancestor.

    Order of preference:
      1. ``:shared:core`` if present in the project (and any module is in :shared).
      2. ``:androidApp:core`` (or similar `*:core`) if all modules are Android-side.
      3. First module in the group (caller marks it as best-effort).
    """
    has_shared = any(m.startswith("shared") for m in modules_in_group)
    registered = set(gradle_modules.values())

    if has_shared and "shared:core" in registered:
        return "shared:core"

    core_candidates = [
        name for name in registered
        if name.endswith(":core") and not name.startswith("shared")
    ]
    if core_candidates and all(not m.startswith("shared") for m in modules_in_group):
        return sorted(core_candidates, key=len)[0]

    return modules_in_group[0]
