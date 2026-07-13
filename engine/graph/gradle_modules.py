"""Gradle multi-module awareness for the graph builder.

Parses ``settings.gradle(.kts)`` to discover declared Gradle modules and maps
each source file to its owning module plus optional KMP source-set.

Works on:
- KMP multi-module projects (`:shared:feature:auth`, `:shared:core`, etc.)
- Android multi-module projects (`:androidApp:feature:bonsai`, ...)
- Mono-module projects (no settings file → first-path-segment fallback)

Pure regex; zero new dependencies.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

# Captures `include(":foo:bar:baz")` / `include(':foo:bar:baz')` / with optional
# extra whitespace. Variants like `include(":foo", ":bar")` are split on commas
# by a second regex below.
_RE_INCLUDE = re.compile(
    r"""include\s*\(\s*((?:['"][^'"]+['"]\s*,?\s*)+)\)""",
    re.MULTILINE,
)
_RE_MODULE_NAME = re.compile(r"""['"]:([\w:\-]+)['"]""")


# Canonical KMP source-set names. Anything else (e.g., `desktopMain`) is
# also accepted as a source_set when present, but the curated set below
# matches what feature-forge can already reason about today.
KMP_SOURCE_SETS: frozenset[str] = frozenset(
    {
        "commonMain",
        "androidMain",
        "iosMain",
        "iosArm64Main",
        "iosSimulatorArm64Main",
        "iosX64Main",
        "jsMain",
        "jvmMain",
        "wasmJsMain",
        "nativeMain",
        "appleMain",
        "commonTest",
        "androidTest",
        "iosTest",
        "jsTest",
        "jvmTest",
        "androidUnitTest",
    }
)


def load_gradle_modules(project_root: Path) -> dict[str, str]:
    """Parse ``settings.gradle(.kts)`` and return ``{dir_path: gradle_module_name}``.

    Example::

        include(":shared:feature:auth")
        # → {"shared/feature/auth": "shared:feature:auth"}

    Multiple include statements are merged. Both ``.kts`` and Groovy
    ``settings.gradle`` flavors are honored — first present wins. Missing
    settings file returns an empty dict (mono-module / non-Gradle project).
    """
    settings_files = [
        project_root / "settings.gradle.kts",
        project_root / "settings.gradle",
    ]
    modules: dict[str, str] = {}
    for settings in settings_files:
        if not settings.exists():
            continue
        try:
            text = settings.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for include_match in _RE_INCLUDE.finditer(text):
            block = include_match.group(1)
            for name_match in _RE_MODULE_NAME.finditer(block):
                gradle_name = name_match.group(1)
                dir_path = gradle_name.replace(":", "/")
                modules[dir_path] = gradle_name
        if modules:
            break
    return modules


def infer_module_and_source_set(
    rel_path: str,
    gradle_modules: dict[str, str],
) -> tuple[str, Optional[str]]:
    """Return ``(module, source_set)`` for a file's repo-relative path.

    - ``module``: longest-prefix match against ``gradle_modules``; fallback to
      first path segment for mono-module / non-Gradle layouts.
    - ``source_set``: first known KMP source-set segment in the path
      (``commonMain`` / ``androidMain`` / ``iosMain`` / etc.) or ``None``.
    """
    rel = rel_path.replace("\\", "/")
    module: Optional[str] = None

    if gradle_modules:
        for prefix in sorted(gradle_modules.keys(), key=len, reverse=True):
            if rel == prefix or rel.startswith(prefix + "/"):
                module = gradle_modules[prefix]
                break

    if module is None:
        parts = [p for p in rel.split("/") if p]
        module = parts[0] if parts else "<root>"

    source_set: Optional[str] = None
    for part in rel.split("/"):
        if part in KMP_SOURCE_SETS:
            source_set = part
            break

    return module, source_set


# Plataforma derivada por source-set KMP explícito. Source-sets fora deste
# mapa (jsMain / wasmJsMain / nativeMain) não têm plataforma mobile-nativa
# e caem em NULL (degrade seguro).
_KMP_PLATFORM_BY_SOURCE_SET: dict[str, str] = {
    "commonMain": "common",
    "commonTest": "common",
    "androidMain": "android",
    "androidTest": "android",
    "androidUnitTest": "android",
    "iosMain": "ios",
    "iosTest": "ios",
    "iosArm64Main": "ios",
    "iosSimulatorArm64Main": "ios",
    "iosX64Main": "ios",
    "appleMain": "ios",
    "jvmMain": "jvm",
    "jvmTest": "jvm",
}

# Diretório de source-set Gradle não-KMP (layout Android/JVM padrão):
# `.../src/<algo>/...` (ex.: `/src/main/`, `/src/debug/`, `/src/release/`).
_SRC_SOURCESET_RE = re.compile(r"(?:^|/)src/[^/]+/")


def infer_platform(
    module: str,
    source_set: Optional[str],
    rel_path: str,
    language: str,
) -> Optional[str]:
    """Derive a file's platform: ``common`` | ``android`` | ``ios`` | ``jvm`` | None.

    Distinta de ``source_set`` (nome literal do source-set KMP): ``platform`` é
    a plataforma *derivada*, para que as reuse-queries enxerguem código
    Android em ``/src/main/`` e Swift em layout Xcode, não só naming KMP.

    - Source-set KMP explícito → plataforma mapeada (``commonMain→common`` etc.).
      Source-sets sem plataforma mobile (``jsMain``/``wasmJsMain``/``nativeMain``)
      → ``None``.
    - Sem source-set KMP: Swift/ObjC → ``ios``; ``.java`` → ``android``;
      Kotlin/XML sob um dir ``src/<sourceSet>/`` (layout Android/JVM padrão)
      → ``android``.
    - Caso contrário → ``None`` (degrade seguro; queries ignoram NULL).
    """
    if source_set is not None:
        return _KMP_PLATFORM_BY_SOURCE_SET.get(source_set)

    rel = rel_path.replace("\\", "/")
    if language in ("swift", "objc"):
        return "ios"
    if language == "java":
        return "android"
    if language in ("kotlin", "xml") and _SRC_SOURCESET_RE.search(rel):
        return "android"
    return None


def module_dir(gradle_name: str) -> str:
    """Convert ``:shared:feature:auth`` (or ``shared:feature:auth``) → ``shared/feature/auth``."""
    name = gradle_name.lstrip(":")
    return name.replace(":", "/")
