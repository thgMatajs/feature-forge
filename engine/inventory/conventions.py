"""Conventions inventory extractor.

Reads structural signals from the project to infer architectural conventions:
DI pattern, navigation framework, folder layout per platform, test framework,
style tooling, primary languages, and package naming.

Heuristics are deliberately conservative — when a signal is missing we mark
the field as `unknown` instead of guessing. Validators downstream can flag
inconsistencies or warn the user to run `forge reconfigure`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from engine.detection._eval import _walk_recursive_pruned
from engine.inventory._walk_cache import walk_project
from engine.utils.paths import inventory_dir
from engine.utils.yaml_io import read_yaml, write_yaml

_SCHEMA_VERSION = 1

_SKIP_DIR_PARTS = {
    "node_modules",
    "build",
    ".gradle",
    ".idea",
    "DerivedData",
    "Pods",
    ".git",
    "worktrees",
    ".claude",
    "dist",
    ".next",
    ".turbo",
}

_NAMESPACE_RE = re.compile(r'namespace\s*=\s*"([^"]+)"')
_APPLICATION_ID_RE = re.compile(r'applicationId\s*=\s*"([^"]+)"')

_JUNIT5_PATTERNS = (
    "org.junit.jupiter.api.",
    "JUnit5Runner",
    "useJUnitPlatform(",
)
# kotlin.test.Test é commonTest do KMP (multi-engine) — NÃO confundir com
# JUnit5 Android. Manter só imports JUnit5 reais + Gradle config.
_JUNIT5_KOTLIN_GREP = ("import org.junit.jupiter.api.",)
_JUNIT5_GRADLE_GREP = ("useJUnitPlatform(",)

_ANDROID_MANIFEST_PACKAGE_RE = re.compile(r'package\s*=\s*"([^"]+)"')
_ANDROID_MANIFEST_LABEL_RE = re.compile(r'android:label\s*=\s*"([^"]+)"')
_ANDROID_MANIFEST_ICON_RE = re.compile(r'android:icon\s*=\s*"([^"]+)"')
# Regex robusta a ordem de atributos: pega o bloco completo da tag <activity ...>
# e extrai atributos separadamente. Antes a regex única exigia name antes de
# exported, perdendo dados quando os atributos vinham trocados.
_ANDROID_MANIFEST_ACTIVITY_BLOCK_RE = re.compile(
    r"<activity\b([^>]*?)/?>",
    re.DOTALL,
)
_ANDROID_MANIFEST_ATTR_RE = re.compile(r'([\w:]+)\s*=\s*"([^"]*)"')
_ANDROID_MANIFEST_PERMISSION_RE = re.compile(
    r'<uses-permission[^>]*android:name\s*=\s*"([^"]+)"'
)

_ANDROID_MANIFEST_LOCATIONS = (
    "app/src/main/AndroidManifest.xml",
    "composeApp/src/main/AndroidManifest.xml",
    "androidApp/src/main/AndroidManifest.xml",
)

_FEATURE_BASES = (
    "androidApp/feature",
    "shared/feature",
    "iosApp/iosApp/Features",
)


@dataclass
class ConventionsInventory:
    di_pattern: str = "unknown"
    navigation_android: str = "unknown"
    navigation_ios: str = "unknown"
    folder_layout: dict[str, str] = field(default_factory=dict)
    test_framework_shared: str = "unknown"
    test_framework_android: str = "unknown"
    test_framework_ios: str = "unknown"
    style_tools: dict[str, str] = field(default_factory=dict)
    primary_languages_per_platform: dict[str, str] = field(default_factory=dict)
    package_naming: dict[str, str] = field(default_factory=dict)
    raw: dict = field(default_factory=dict)


def _should_skip(rel: Path) -> bool:
    return any(part in _SKIP_DIR_PARTS for part in rel.parts)


def _grep_any(project_root: Path, patterns: tuple[str, ...], suffix: str, limit: int = 3) -> list[Path]:
    # Usa walk cache compartilhado: subsequentes chamadas para mesmo suffix reusam.
    hits: list[Path] = []
    for path in walk_project(str(project_root), (suffix,)):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if any(p in text for p in patterns):
            hits.append(path)
            if len(hits) >= limit:
                break
    return hits


def _detect_di(project_root: Path) -> str:
    if _grep_any(project_root, ("@KoinViewModel", "@ComponentScan", "org.koin.core.annotation"), ".kt", limit=1):
        return "koin-annotations"
    if _grep_any(project_root, ("@HiltAndroidApp", "dagger.hilt"), ".kt", limit=1):
        return "hilt"
    if _grep_any(project_root, ("import org.koin",), ".kt", limit=1):
        return "koin-dsl"
    if _grep_any(project_root, ("import dagger",), ".kt", limit=1):
        return "dagger"
    return "unknown"


def _detect_nav_android(project_root: Path) -> str:
    if _grep_any(
        project_root,
        ("NavDisplay", "EntryProviderInstaller", "androidx.navigation3"),
        ".kt",
        limit=1,
    ):
        return "nav3"
    if _grep_any(project_root, ("NavHost", "androidx.navigation.compose"), ".kt", limit=1):
        return "nav2"
    return "unknown"


def _detect_nav_ios(project_root: Path) -> str:
    if _grep_any(project_root, ("NavigationStack",), ".swift", limit=1):
        return "swiftui-navigation"
    if _grep_any(project_root, ("UINavigationController",), ".swift", limit=1):
        return "uikit"
    return "unknown"


def _detect_test_frameworks(project_root: Path) -> tuple[str, str, str]:
    shared = "unknown"
    if _grep_any(project_root, ("kotlin.test", "kotlin-test"), ".kt", limit=1):
        shared = "kotlin-test"
    android = "unknown"
    if _grep_any(project_root, _JUNIT5_KOTLIN_GREP, ".kt", limit=1) or _grep_any(
        project_root, _JUNIT5_GRADLE_GREP, ".kts", limit=1
    ):
        android = "junit5"
    elif _grep_any(project_root, ("org.junit.jupiter", "junit-jupiter"), ".kt", limit=1):
        android = "junit5"
    elif _grep_any(project_root, ("org.junit.Test", "junit.framework"), ".kt", limit=1):
        android = "junit4"
    ios = "unknown"
    if _grep_any(project_root, ("import Testing",), ".swift", limit=1):
        ios = "swift-testing"
    elif _grep_any(project_root, ("import XCTest",), ".swift", limit=1):
        ios = "xctest"
    return shared, android, ios


def _detect_style_tools(project_root: Path) -> dict[str, str]:
    tools: dict[str, list[str]] = {"swift": [], "kotlin": [], "web": []}
    if (project_root / ".swiftlint.yml").exists():
        tools["swift"].append("swiftlint")
    if (project_root / ".swiftformat").exists():
        tools["swift"].append("swiftformat")
    if (project_root / "config" / "detekt" / "detekt.yml").exists():
        tools["kotlin"].append("detekt")
    elif list(project_root.glob("**/detekt*.yml"))[:1]:
        tools["kotlin"].append("detekt")
    if (project_root / ".editorconfig").exists():
        tools["kotlin"].append("ktlint")
    # F6: glob `webApp/.eslintrc*` já cobre o arquivo exato `.eslintrc` —
    # check explícito removido (dead code).
    if any(project_root.glob("webApp/.eslintrc*")):
        tools["web"].append("eslint")
    if any(project_root.glob("webApp/.prettierrc*")):
        tools["web"].append("prettier")
    return {k: "+".join(sorted(set(v))) for k, v in tools.items() if v}


def _detect_languages(project_root: Path) -> dict[str, str]:
    langs: dict[str, str] = {}
    if any(project_root.glob("**/*.kt")):
        langs["android"] = "kotlin"
        langs["shared"] = "kotlin"
    if any(project_root.glob("iosApp/**/*.swift")) or any(project_root.glob("**/*.swift")):
        langs["ios"] = "swift"
    if any(project_root.glob("webApp/**/*.tsx")) or any(project_root.glob("**/*.tsx")):
        langs["web"] = "typescript"
    return dict(sorted(langs.items()))


def _detect_package_naming(project_root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for gradle in project_root.glob("**/build.gradle.kts"):
        rel = gradle.relative_to(project_root)
        if _should_skip(rel):
            continue
        try:
            text = gradle.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        ns = _NAMESPACE_RE.search(text)
        if ns:
            if "composeApp" in str(rel) or "androidApp" in str(rel):
                out.setdefault("android", ns.group(1))
            elif "shared" in str(rel):
                out.setdefault("shared", ns.group(1))
        app_id = _APPLICATION_ID_RE.search(text)
        if app_id:
            out.setdefault("application-id", app_id.group(1))
    pbxproj = list(project_root.glob("iosApp/*.xcodeproj/project.pbxproj"))
    if pbxproj:
        try:
            text = pbxproj[0].read_text(encoding="utf-8", errors="ignore")
            bundle_match = re.search(r"PRODUCT_BUNDLE_IDENTIFIER\s*=\s*([^;\s]+);", text)
            if bundle_match:
                out["ios-bundle"] = bundle_match.group(1).strip('"')
        except OSError:
            pass
    return dict(sorted(out.items()))


def _parse_android_manifest(project_root: Path) -> dict:
    """Parse AndroidManifest.xml em locations canônicos.

    Retorna dict com chaves: package, application_label, application_icon,
    main_activity, main_activity_exported, permissions. Falhas silenciosas
    em XMLs muito dinâmicos ou ausentes.
    """
    info: dict = {}
    manifest: Optional[Path] = None
    for loc in _ANDROID_MANIFEST_LOCATIONS:
        cand = project_root / loc
        if cand.exists():
            manifest = cand
            break
    if manifest is None:
        return info
    try:
        text = manifest.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return info
    pkg = _ANDROID_MANIFEST_PACKAGE_RE.search(text)
    if pkg:
        info["package"] = pkg.group(1)
    label = _ANDROID_MANIFEST_LABEL_RE.search(text)
    if label:
        info["application_label"] = label.group(1)
    icon = _ANDROID_MANIFEST_ICON_RE.search(text)
    if icon:
        info["application_icon"] = icon.group(1)
    # Parse anchored: pega cada <activity ...> e extrai attrs independente da
    # ordem em que aparecem na tag.
    for match in _ANDROID_MANIFEST_ACTIVITY_BLOCK_RE.finditer(text):
        attrs = dict(_ANDROID_MANIFEST_ATTR_RE.findall(match.group(1)))
        name = attrs.get("android:name")
        if not name:
            continue
        info["main_activity"] = name
        exported = attrs.get("android:exported")
        if exported is not None:
            info["main_activity_exported"] = exported == "true"
        break
    perms = [m.group(1) for m in _ANDROID_MANIFEST_PERMISSION_RE.finditer(text)]
    if perms:
        info["permissions"] = sorted(set(perms))
    info["manifest_path"] = str(manifest.relative_to(project_root))
    return info


def _count_features(project_root: Path) -> int:
    """Conta feature modules ativas (presente no shared OU em qualquer platform).

    Une nomes encontrados em:
    - androidApp/feature/*/
    - shared/feature/*/
    - iosApp/iosApp/Features/*/
    """
    found: set[str] = set()
    for base in _FEATURE_BASES:
        base_path = project_root / base
        if not base_path.exists() or not base_path.is_dir():
            continue
        for child in base_path.iterdir():
            if not child.is_dir():
                continue
            if child.name.startswith(".") or child.name in _SKIP_DIR_PARTS:
                continue
            found.add(child.name.lower())
    return len(found)


def _detect_folder_layout(project_root: Path) -> dict[str, str]:
    layout: dict[str, str] = {}
    # BUG-5: `_walk_recursive_pruned` poda `_SKIP_DIR_PARTS` na descida. As
    # checagens abaixo são `any(...)` booleanas — ordem não afeta resultado.
    has_android_screen_files = any(
        p.name.endswith("Screen.kt")
        for p in _walk_recursive_pruned(project_root, "*Screen.kt", _SKIP_DIR_PARTS)
        if not _should_skip(p.relative_to(project_root))
    )
    has_android_content_files = any(
        p.name.endswith("Content.kt")
        for p in _walk_recursive_pruned(project_root, "*Content.kt", _SKIP_DIR_PARTS)
        if not _should_skip(p.relative_to(project_root))
    )
    if has_android_screen_files and has_android_content_files:
        layout["android"] = "{Screen}Screen.kt + {Screen}Content.kt + {Screen}Components.kt + {Screen}Mappers.kt"
    elif has_android_screen_files:
        layout["android"] = "{Screen}Screen.kt"

    has_ios_screen_view = any(
        p.name.endswith("ScreenView.swift")
        for p in _walk_recursive_pruned(
            project_root, "*ScreenView.swift", _SKIP_DIR_PARTS
        )
        if not _should_skip(p.relative_to(project_root))
    )
    has_ios_content_view = any(
        p.name.endswith("ScreenContentView.swift")
        for p in _walk_recursive_pruned(
            project_root, "*ScreenContentView.swift", _SKIP_DIR_PARTS
        )
        if not _should_skip(p.relative_to(project_root))
    )
    if has_ios_screen_view and has_ios_content_view:
        layout["ios"] = "{Screen}ScreenView.swift + {Screen}ScreenContentView.swift + {Screen}Components.swift"
    elif has_ios_screen_view:
        layout["ios"] = "{Screen}ScreenView.swift"

    has_viewmodel = any(
        p.name.endswith("ViewModel.kt")
        for p in _walk_recursive_pruned(project_root, "*ViewModel.kt", _SKIP_DIR_PARTS)
        if not _should_skip(p.relative_to(project_root))
    )
    if has_viewmodel:
        layout["shared"] = "ViewModel + UseCase(s) + Repository (impl + interface)"
    return layout


def _detect_state_pattern(project_root: Path) -> dict[str, str]:
    if _grep_any(project_root, ("StateUI<", "sealed class StateUI"), ".kt", limit=1):
        return {"name": "stateui", "type": "StateUI<T>"}
    if _grep_any(project_root, ("StateFlow<",), ".kt", limit=1):
        return {"name": "stateflow-pure", "type": "StateFlow<T>"}
    return {"name": "unknown", "type": "unknown"}


def _detect_branch_pattern(project_root: Path) -> dict[str, list[str]]:
    return {
        "pattern": "feature/{slug}",
        "examples": [],
    }


def extract_conventions(project_root: Path) -> ConventionsInventory:
    """Extract architectural and tooling conventions from the project root."""
    di = _detect_di(project_root)
    nav_android = _detect_nav_android(project_root)
    nav_ios = _detect_nav_ios(project_root)
    test_shared, test_android, test_ios = _detect_test_frameworks(project_root)
    style_tools = _detect_style_tools(project_root)
    languages = _detect_languages(project_root)
    package_naming = _detect_package_naming(project_root)
    folder_layout = _detect_folder_layout(project_root)
    state_pattern = _detect_state_pattern(project_root)
    manifest_info = _parse_android_manifest(project_root)
    if manifest_info.get("package") and "android-manifest" not in package_naming:
        package_naming["android-manifest"] = manifest_info["package"]
    features_count = _count_features(project_root)

    raw = {
        "schema-version": _SCHEMA_VERSION,
        "last-scan": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "extraction": {
            "features-analyzed": features_count,
            "confidence": 0.7,
        },
        "folder-layout": folder_layout,
        "state-pattern": state_pattern,
        "di-pattern": {
            "name": di,
            "ios-strategy": "factory-functions" if di == "koin-annotations" else "unknown",
            "ios-factory-naming": "create{ClassName}()" if di == "koin-annotations" else None,
        },
        "navigation": {
            "android": nav_android,
            "ios": nav_ios,
        },
        "test-pattern": {
            "frameworks": {
                "shared": test_shared,
                "android": test_android,
                "ios": test_ios,
            },
            "flow-assertion": "turbine" if _grep_any(project_root, ("app.cash.turbine",), ".kt", limit=1) else "unknown",
            "type-assertion": "assertIs<T>()",
            "fakes-vs-mocks": "fakes-preferred",
        },
        "style-tools": style_tools,
        "languages": languages,
        "package-naming": package_naming,
        "android-manifest-info": manifest_info,
        "branch": _detect_branch_pattern(project_root),
        "commit": {
            "format": "conventional-commits",
        },
        "quality": {
            "cyclomatic-complexity-max": 15,
            "block-depth-max": 4,
            "lines-per-class-max": 600,
            "functions-per-class-max": 15,
        },
        "conflicts-detected": [],
    }

    return ConventionsInventory(
        di_pattern=di,
        navigation_android=nav_android,
        navigation_ios=nav_ios,
        folder_layout=folder_layout,
        test_framework_shared=test_shared,
        test_framework_android=test_android,
        test_framework_ios=test_ios,
        style_tools=style_tools,
        primary_languages_per_platform=languages,
        package_naming=package_naming,
        raw=raw,
    )


def write_conventions_inventory(project_root: Path, inv: ConventionsInventory) -> Path:
    out = inventory_dir(project_root) / "conventions.yaml"
    write_yaml(out, inv.raw, atomic=True)
    return out


def read_conventions_inventory(project_root: Path) -> Optional[ConventionsInventory]:
    path = inventory_dir(project_root) / "conventions.yaml"
    if not path.exists():
        return None
    raw = read_yaml(path) or {}
    di = (raw.get("di-pattern") or {}).get("name", "unknown")
    nav = raw.get("navigation") or {}
    tp = (raw.get("test-pattern") or {}).get("frameworks") or {}
    return ConventionsInventory(
        di_pattern=di,
        navigation_android=nav.get("android", "unknown"),
        navigation_ios=nav.get("ios", "unknown"),
        folder_layout=dict(raw.get("folder-layout") or {}),
        test_framework_shared=tp.get("shared", "unknown"),
        test_framework_android=tp.get("android", "unknown"),
        test_framework_ios=tp.get("ios", "unknown"),
        style_tools=dict(raw.get("style-tools") or {}),
        primary_languages_per_platform=dict(raw.get("languages") or {}),
        package_naming=dict(raw.get("package-naming") or {}),
        raw=raw,
    )


def diff_conventions(old: ConventionsInventory, new: ConventionsInventory) -> dict:
    """Return mapping of field-name to (old_value, new_value) for changed fields."""
    diffs: dict[str, tuple] = {}
    fields = (
        "di_pattern",
        "navigation_android",
        "navigation_ios",
        "folder_layout",
        "test_framework_shared",
        "test_framework_android",
        "test_framework_ios",
        "style_tools",
        "primary_languages_per_platform",
        "package_naming",
    )
    for name in fields:
        old_val = getattr(old, name)
        new_val = getattr(new, name)
        if old_val != new_val:
            diffs[name] = (old_val, new_val)
    return diffs
