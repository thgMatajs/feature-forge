"""Design-system inventory extractor.

Walks the project root, detects design-system components (atoms / molecules /
organisms) and design tokens (colors / spacing / radius / typography), then
serializes the result into `.claude/inventory/design-system.yaml` per the
schema documented in `docs/schemas/inventories.md`.

Heurística:
- Componentes: arquivos `Meo*.{kt,swift,tsx}` em paths convencionais.
- Tokens: melhor esforço via regex em arquivos canônicos (`Spacing.kt`,
  `CornerRadius.kt`, `MeoBonsaiColors.kt`, `MeoBonsaiTypography.kt`,
  `index.css`, `tailwind.config.*`, `TokensCatalog.swift`).

False positives são aceitáveis — validators downstream consolidam.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from engine.detection._eval import _walk_recursive_pruned
from engine.inventory._walk_cache import walk_project
from engine.utils.paths import inventory_dir
from engine.utils.yaml_io import read_yaml, write_yaml

_SCHEMA_VERSION = 1

_ANDROID_ATOM_HINTS = ("/components/atoms/", "/atoms/")
_ANDROID_MOL_HINTS = ("/components/molecules/", "/molecules/")
_IOS_ATOM_HINTS = ("/DesignSystem/Atoms/", "/Atoms/")
_IOS_MOL_HINTS = ("/DesignSystem/Molecules/", "/Molecules/")
_WEB_ATOM_HINTS = ("/components/atoms/", "/atoms/")
_WEB_MOL_HINTS = ("/components/molecules/", "/molecules/")

_DEFAULT_NAMING = "Meo*"
_ALTERNATIVE_NAMING = ["App*", "Ds*", "DS*", "Ui*"]

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

_HEX_RE = re.compile(r"#[0-9A-Fa-f]{6,8}")
_KOTLIN_HEX_CONST_RE = re.compile(
    r'^\s*const\s+val\s+([A-Z][A-Z0-9_]*)\s*=\s*"(#[0-9A-Fa-f]{6,8})"',
    re.MULTILINE,
)
_KOTLIN_INT_CONST_RE = re.compile(
    r"^\s*const\s+val\s+([A-Z][A-Z0-9_]*)\s*=\s*(\d+)\s*$",
    re.MULTILINE,
)
_KOTLIN_FLOAT_CONST_RE = re.compile(
    r"^\s*const\s+val\s+([A-Z][A-Z0-9_]*)\s*=\s*([\d.]+)f?\s*$",
    re.MULTILINE,
)
_KOTLIN_STR_CONST_RE = re.compile(
    r'^\s*const\s+val\s+([A-Z][A-Z0-9_]*)\s*=\s*"([^"]+)"',
    re.MULTILINE,
)
_CSS_COLOR_VAR_RE = re.compile(r"--color-([a-zA-Z0-9-]+)\s*:\s*(#[0-9A-Fa-f]{6,8})")
_CSS_SPACING_VAR_RE = re.compile(r"--spacing-([a-zA-Z0-9-]+)\s*:\s*(\d+)px")
_CSS_RADIUS_VAR_RE = re.compile(r"--(?:radius|rounded)-([a-zA-Z0-9-]+)\s*:\s*(\d+)px")

_TAILWIND_COLORS_BLOCK_RE = re.compile(
    r"colors\s*:\s*\{(.*?)\n\s*\}",
    re.DOTALL,
)
_TAILWIND_SPACING_BLOCK_RE = re.compile(
    r"spacing\s*:\s*\{(.*?)\n\s*\}",
    re.DOTALL,
)
_TAILWIND_RADIUS_BLOCK_RE = re.compile(
    r"borderRadius\s*:\s*\{(.*?)\n\s*\}",
    re.DOTALL,
)
_TAILWIND_FONT_BLOCK_RE = re.compile(
    r"fontFamily\s*:\s*\{(.*?)\n\s*\}",
    re.DOTALL,
)
_TAILWIND_KV_RE = re.compile(
    r"""['"]?([a-zA-Z0-9_-]+)['"]?\s*:\s*['"]([^'"]+)['"]""",
)


@dataclass
class DSComponent:
    name: str
    level: str
    status: str
    paths: dict[str, str] = field(default_factory=dict)
    has_preview: bool = False


@dataclass
class DSTokens:
    colors: dict[str, str] = field(default_factory=dict)
    spacing: dict[str, int] = field(default_factory=dict)
    radius: dict[str, int] = field(default_factory=dict)
    typography: dict[str, str] = field(default_factory=dict)


@dataclass
class DesignSystemInventory:
    components: list[DSComponent] = field(default_factory=list)
    tokens: DSTokens = field(default_factory=DSTokens)
    raw: dict = field(default_factory=dict)


def _should_skip(path: Path) -> bool:
    return any(part in _SKIP_DIR_PARTS for part in path.parts)


def _iter_files(root: Path, suffix: str) -> list[Path]:
    # Usa walk cache compartilhado: a 1ª chamada paga o custo, próximas reusam.
    return list(walk_project(str(root), (suffix,)))


def _level_for(path_str: str, atom_hints: tuple[str, ...], mol_hints: tuple[str, ...]) -> str:
    if any(h in path_str for h in atom_hints):
        return "atom"
    if any(h in path_str for h in mol_hints):
        return "molecule"
    if "/organisms/" in path_str or "/Organisms/" in path_str:
        return "organism"
    return "unknown"


def _has_preview(path: Path, marker: str) -> bool:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return marker in text


def _detect_naming_pattern(names: list[str]) -> tuple[str, list[str]]:
    """Detect dominant prefix among component names. Returns (pattern, alternatives)."""
    prefixes: Counter[str] = Counter()
    for n in names:
        match = re.match(r"^([A-Z][a-z]+|[A-Z]{2,})", n)
        if match:
            prefixes[match.group(1)] += 1
    if not prefixes:
        return ("unknown", [])
    top = prefixes.most_common(1)[0][0]
    return (f"{top}*", _ALTERNATIVE_NAMING)


def _scan_android_components(project_root: Path) -> list[DSComponent]:
    components: list[DSComponent] = []
    for path in _iter_files(project_root, ".kt"):
        rel = str(path.relative_to(project_root))
        if "/designsystem/" not in rel.lower() and "/components/" not in rel:
            continue
        if "test" in rel.lower() or "Catalog" in path.name:
            continue
        name = path.stem
        if name.endswith("TestTags") or name.endswith("Strings") or name.endswith("Tokens"):
            continue
        if not re.match(r"^[A-Z][A-Za-z0-9]+$", name):
            continue
        level = _level_for(rel, _ANDROID_ATOM_HINTS, _ANDROID_MOL_HINTS)
        if level == "unknown":
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
                level = _infer_component_level(path, content, _count_imports(content, ".kt"))
            except OSError:
                continue
        components.append(
            DSComponent(
                name=name,
                level=level,
                status="beta",
                paths={"android": rel},
                has_preview=_has_preview(path, "@Preview"),
            )
        )
    return components


def _scan_ios_components(project_root: Path) -> list[DSComponent]:
    components: list[DSComponent] = []
    for path in _iter_files(project_root, ".swift"):
        rel = str(path.relative_to(project_root))
        if "/DesignSystem/" not in rel:
            continue
        if "/Catalog/" in rel or "Catalog.swift" in path.name:
            continue
        name = path.stem
        if name.endswith("TestTags") or name.endswith("Strings"):
            continue
        if not re.match(r"^[A-Z][A-Za-z0-9]+$", name):
            continue
        level = _level_for(rel, _IOS_ATOM_HINTS, _IOS_MOL_HINTS)
        if level == "unknown":
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
                level = _infer_component_level(path, content, _count_imports(content, ".swift"))
            except OSError:
                continue
        components.append(
            DSComponent(
                name=name,
                level=level,
                status="beta",
                paths={"ios": rel},
                has_preview=_has_preview(path, "#Preview"),
            )
        )
    return components


def _scan_web_components(project_root: Path) -> list[DSComponent]:
    components: list[DSComponent] = []
    for path in _iter_files(project_root, ".tsx"):
        rel = str(path.relative_to(project_root))
        if "/components/" not in rel:
            continue
        if path.name.endswith(".test.tsx") or path.name.endswith(".stories.tsx"):
            continue
        name = path.stem
        if not re.match(r"^[A-Z][A-Za-z0-9]+$", name):
            continue
        level = _level_for(rel, _WEB_ATOM_HINTS, _WEB_MOL_HINTS)
        if level == "unknown":
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
                level = _infer_component_level(path, content, _count_imports(content, ".tsx"))
            except OSError:
                continue
        components.append(
            DSComponent(
                name=name,
                level=level,
                status="beta",
                paths={"web": rel},
            )
        )
    return components


def _merge_components(buckets: list[list[DSComponent]]) -> list[DSComponent]:
    by_name: dict[str, DSComponent] = {}
    for bucket in buckets:
        for c in bucket:
            existing = by_name.get(c.name)
            if existing is None:
                by_name[c.name] = DSComponent(
                    name=c.name,
                    level=c.level,
                    status=c.status,
                    paths=dict(c.paths),
                    has_preview=c.has_preview,
                )
                continue
            existing.paths.update(c.paths)
            existing.has_preview = existing.has_preview or c.has_preview
            if existing.level == "unknown" and c.level != "unknown":
                existing.level = c.level
    return sorted(by_name.values(), key=lambda c: c.name)


def _extract_kotlin_token_object(file_path: Path) -> dict[str, int]:
    try:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return {}
    result: dict[str, int] = {}
    for match in _KOTLIN_INT_CONST_RE.finditer(text):
        name = match.group(1).lower()
        try:
            result[name] = int(match.group(2))
        except ValueError:
            continue
    return dict(sorted(result.items()))


def _extract_kotlin_colors(file_path: Path) -> dict[str, str]:
    try:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return {}
    result: dict[str, str] = {}
    for match in _KOTLIN_HEX_CONST_RE.finditer(text):
        name = match.group(1).lower()
        result[name] = match.group(2)
    return dict(sorted(result.items()))


def _extract_kotlin_typography(file_path: Path) -> dict[str, str]:
    try:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return {}
    result: dict[str, str] = {}
    for match in _KOTLIN_STR_CONST_RE.finditer(text):
        name = match.group(1).lower()
        value = match.group(2)
        if any(k in name for k in ("headline", "body", "title", "label", "display")):
            result[name] = value
    return dict(sorted(result.items()))


def _extract_css_tokens(file_path: Path) -> tuple[dict[str, str], dict[str, int], dict[str, int]]:
    try:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ({}, {}, {})
    colors: dict[str, str] = {}
    spacing: dict[str, int] = {}
    radius: dict[str, int] = {}
    for match in _CSS_COLOR_VAR_RE.finditer(text):
        colors[match.group(1)] = match.group(2)
    for match in _CSS_SPACING_VAR_RE.finditer(text):
        try:
            spacing[match.group(1)] = int(match.group(2))
        except ValueError:
            continue
    for match in _CSS_RADIUS_VAR_RE.finditer(text):
        try:
            radius[match.group(1)] = int(match.group(2))
        except ValueError:
            continue
    return (dict(sorted(colors.items())), dict(sorted(spacing.items())), dict(sorted(radius.items())))


def _extract_brace_block(content: str, key: str) -> Optional[str]:
    """Extrai bloco `{ ... }` correspondente a `key:` usando contagem de braces.

    Regex baseada em `\\{(.*?)\\n\\s*\\}` quebra em configs com cores nested
    (ex.: `colors: { primary: { 500: '#...', 600: '#...' } }`). Este helper
    encontra `key:`, localiza o próximo `{`, e percorre o texto contando braces
    até fechar o nível original — retornando o conteúdo entre os braces externos.
    """
    idx = content.find(f"{key}:")
    if idx < 0:
        return None
    brace_start = content.find("{", idx)
    if brace_start < 0:
        return None
    depth = 1
    i = brace_start + 1
    while i < len(content) and depth > 0:
        ch = content[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        i += 1
    if depth != 0:
        return None
    return content[brace_start + 1 : i - 1]


def _parse_tailwind_config(config_path: Path) -> dict[str, dict]:
    """Best-effort parser para tailwind.config.{js,ts}.

    Retorna {'colors': {...}, 'spacing': {...}, 'radius': {...}, 'typography': {...}}.
    Falha silenciosa em configs muito dinâmicos (spread, imports, functions).
    """
    out: dict[str, dict] = {"colors": {}, "spacing": {}, "radius": {}, "typography": {}}
    try:
        text = config_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return out

    colors_block = _extract_brace_block(text, "colors")
    if colors_block:
        for m in _TAILWIND_KV_RE.finditer(colors_block):
            out["colors"][m.group(1)] = m.group(2)

    spacing_block = _extract_brace_block(text, "spacing")
    if spacing_block:
        for m in _TAILWIND_KV_RE.finditer(spacing_block):
            value = m.group(2).replace("px", "").replace("rem", "").strip()
            try:
                out["spacing"][m.group(1)] = int(float(value))
            except ValueError:
                continue

    radius_block = _extract_brace_block(text, "borderRadius")
    if radius_block:
        for m in _TAILWIND_KV_RE.finditer(radius_block):
            value = m.group(2).replace("px", "").replace("rem", "").strip()
            try:
                out["radius"][m.group(1)] = int(float(value))
            except ValueError:
                continue

    font_block = _extract_brace_block(text, "fontFamily")
    if font_block:
        for m in _TAILWIND_KV_RE.finditer(font_block):
            out["typography"][m.group(1)] = m.group(2)

    return out


def _infer_component_level(file_path: Path, content: str, imports: list[str]) -> str:
    """Fallback heurístico para level quando path-hint não resolve.

    Ordem:
    1. LOC < 80 AND imports ≤ 3 → atom
    2. LOC < 200 AND imports ≤ 8 → molecule
    3. else → organism
    """
    loc = content.count("\n") + 1
    n_imports = len(imports)
    if loc < 80 and n_imports <= 3:
        return "atom"
    if loc < 200 and n_imports <= 8:
        return "molecule"
    return "organism"


def _count_imports(content: str, suffix: str) -> list[str]:
    """Conta imports de forma simplificada por linguagem."""
    if suffix in (".kt", ".swift"):
        return [ln for ln in content.splitlines() if ln.lstrip().startswith("import ")]
    if suffix == ".tsx":
        return [
            ln
            for ln in content.splitlines()
            if ln.lstrip().startswith("import ")
        ]
    return []


def _extract_tokens(project_root: Path) -> DSTokens:
    tokens = DSTokens()

    # BUG-5: `_walk_recursive_pruned` poda `_SKIP_DIR_PARTS` na descida e
    # ORDENA a saída — o `break` no 1º match abaixo fica DETERMINÍSTICO
    # (rglob nativo era inode-order; com 2 `Spacing.kt` o vencedor variava).
    def _find(pat: str) -> list[Path]:
        return list(_walk_recursive_pruned(project_root, pat, _SKIP_DIR_PARTS))

    candidates_spacing = _find("Spacing.kt") + _find("Spacing.swift")
    candidates_radius = (
        _find("CornerRadius.kt") + _find("BorderRadius.kt") + _find("Radius.swift")
    )
    candidates_colors = (
        _find("MeoBonsaiColors.kt") + _find("Colors.kt") + _find("Color.kt")
    )
    candidates_typo = _find("*Typography.kt") + _find("FontFamilies.kt")

    for cand in candidates_spacing:
        if _should_skip(cand.relative_to(project_root)):
            continue
        tokens.spacing.update(_extract_kotlin_token_object(cand))
        if tokens.spacing:
            break

    for cand in candidates_radius:
        if _should_skip(cand.relative_to(project_root)):
            continue
        tokens.radius.update(_extract_kotlin_token_object(cand))
        if tokens.radius:
            break

    for cand in candidates_colors:
        if _should_skip(cand.relative_to(project_root)):
            continue
        tokens.colors.update(_extract_kotlin_colors(cand))
        if tokens.colors:
            break

    for cand in candidates_typo:
        if _should_skip(cand.relative_to(project_root)):
            continue
        tokens.typography.update(_extract_kotlin_typography(cand))
        if tokens.typography:
            break

    css_candidates = _find("index.css") + _find("globals.css")
    for cand in css_candidates:
        if _should_skip(cand.relative_to(project_root)):
            continue
        css_colors, css_spacing, css_radius = _extract_css_tokens(cand)
        if not tokens.colors:
            tokens.colors.update(css_colors)
        if not tokens.spacing:
            tokens.spacing.update(css_spacing)
        if not tokens.radius:
            tokens.radius.update(css_radius)
        break

    tailwind_candidates: list[Path] = []
    for stem in ("tailwind.config.js", "tailwind.config.ts"):
        for base in ("webApp", "."):
            cand = project_root / base / stem if base != "." else project_root / stem
            if cand.exists():
                tailwind_candidates.append(cand)
    for cand in tailwind_candidates:
        if _should_skip(cand.relative_to(project_root)):
            continue
        tw = _parse_tailwind_config(cand)
        for key, value in tw.get("colors", {}).items():
            tokens.colors.setdefault(key, value)
        for key, value in tw.get("spacing", {}).items():
            tokens.spacing.setdefault(key, value)
        for key, value in tw.get("radius", {}).items():
            tokens.radius.setdefault(key, value)
        for key, value in tw.get("typography", {}).items():
            tokens.typography.setdefault(key, value)

    tokens.colors = dict(sorted(tokens.colors.items()))
    tokens.spacing = dict(sorted(tokens.spacing.items()))
    tokens.radius = dict(sorted(tokens.radius.items()))
    tokens.typography = dict(sorted(tokens.typography.items()))
    return tokens


def _detect_base_paths(components: list[DSComponent]) -> dict[str, str]:
    base: dict[str, set[str]] = {"android": set(), "ios": set(), "web": set()}
    for c in components:
        for platform, p in c.paths.items():
            parts = p.split("/")
            anchors = {"designsystem", "DesignSystem", "components"}
            for i, part in enumerate(parts):
                if part in anchors:
                    base.setdefault(platform, set()).add("/".join(parts[: i + 1]))
                    break
    return {plat: sorted(paths)[0] for plat, paths in base.items() if paths}


def _coverage(
    components: list[DSComponent],
    legacy: list[DSComponent] | None = None,
) -> dict:
    legacy = legacy or []
    by_level: Counter[str] = Counter(c.level for c in components)
    by_status: Counter[str] = Counter(c.status for c in components)
    android = {c.name for c in components if "android" in c.paths}
    ios = {c.name for c in components if "ios" in c.paths}
    web = {c.name for c in components if "web" in c.paths}
    android_ios_overlap = android & ios
    parity = (len(android_ios_overlap) / max(len(android | ios), 1)) if (android or ios) else 0.0
    # F1: total agora soma canonical + legacy quando legacy é passado, com
    # contagens explícitas para callers distinguirem sem inspecionar a lista.
    legacy_count = len(legacy)
    return {
        "total-components": len(components) + legacy_count,
        "canonical-count": len(components),
        "legacy-count": legacy_count,
        "by-level": dict(sorted(by_level.items())),
        "by-status": dict(sorted(by_status.items())),
        "parity": {
            "android-ios": round(parity, 2),
            "android-only": sorted(android - ios),
            "ios-only": sorted(ios - android),
            "web-only": sorted(web - (android | ios)),
        },
    }


def extract_design_system(project_root: Path) -> DesignSystemInventory:
    """Walk project_root, identify DS components and tokens."""
    android = _scan_android_components(project_root)
    ios = _scan_ios_components(project_root)
    web = _scan_web_components(project_root)
    components = _merge_components([android, ios, web])
    tokens = _extract_tokens(project_root)

    all_names = [c.name for c in components]
    naming_pattern, alternatives = _detect_naming_pattern(all_names)
    if naming_pattern == "unknown":
        naming_pattern = _DEFAULT_NAMING

    # F1: criar novos objetos via dataclasses.replace para não mutar a lista
    # compartilhada `components` (caller pode consumir `inv.components` depois).
    canonical: list[DSComponent] = []
    legacy: list[DSComponent] = []
    prefix = naming_pattern.rstrip("*")
    for c in components:
        if prefix and c.name.startswith(prefix):
            canonical.append(replace(c, status="canonical"))
        else:
            legacy.append(replace(c, status="legacy"))

    raw = {
        "schema-version": _SCHEMA_VERSION,
        "last-scan": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "scan-confidence": 0.8,
        "detection": {
            "naming-pattern": naming_pattern,
            "alternative-patterns-considered": alternatives,
            "base-paths": _detect_base_paths(canonical or components),
        },
        "components": [
            {
                "id": _slugify(c.name),
                "name": c.name,
                "level": c.level,
                "status": c.status,
                "paths": dict(sorted(c.paths.items())),
                "has-preview": c.has_preview,
            }
            for c in canonical
        ],
        "tokens": {
            "colors": {
                "pattern": "semantic" if tokens.colors else "unknown",
                "values": tokens.colors,
            },
            "spacing": {
                "pattern": "named" if tokens.spacing else "unknown",
                "values": tokens.spacing,
            },
            "radii": {
                "pattern": "named" if tokens.radius else "unknown",
                "values": tokens.radius,
            },
            "typography": {
                "values": tokens.typography,
            },
        },
        "coverage": _coverage(canonical, legacy),
        "legacy-components": [
            {
                "id": _slugify(c.name),
                "name": c.name,
                "paths": dict(sorted(c.paths.items())),
                "status": c.status,
            }
            for c in legacy
        ],
    }

    inv = DesignSystemInventory(components=components, tokens=tokens, raw=raw)
    return inv


def _slugify(name: str) -> str:
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", name)
    return s.lower()


def write_design_system_inventory(project_root: Path, inv: DesignSystemInventory) -> Path:
    out = inventory_dir(project_root) / "design-system.yaml"
    write_yaml(out, inv.raw, atomic=True)
    return out


def read_design_system_inventory(project_root: Path) -> Optional[DesignSystemInventory]:
    path = inventory_dir(project_root) / "design-system.yaml"
    if not path.exists():
        return None
    raw = read_yaml(path) or {}
    components = [
        DSComponent(
            name=c["name"],
            level=c.get("level", "unknown"),
            status=c.get("status", "unknown"),
            paths=dict(c.get("paths") or {}),
            has_preview=bool(c.get("has-preview", False)),
        )
        for c in raw.get("components") or []
    ]
    tokens_raw = raw.get("tokens") or {}
    tokens = DSTokens(
        colors=dict((tokens_raw.get("colors") or {}).get("values") or {}),
        spacing=dict((tokens_raw.get("spacing") or {}).get("values") or {}),
        radius=dict((tokens_raw.get("radii") or {}).get("values") or {}),
        typography=dict((tokens_raw.get("typography") or {}).get("values") or {}),
    )
    return DesignSystemInventory(components=components, tokens=tokens, raw=raw)
