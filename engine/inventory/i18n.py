"""i18n inventory extractor.

Detects the i18n source-of-truth (preferred: JSON per locale, MeoBonsai-style
under `shared/resources/i18n/`), enumerates keys with nested-flattening, and
serializes a snapshot to `.claude/inventory/i18n.yaml` per the schema in
`docs/schemas/inventories.md`.

Generated artifacts (Android `strings.xml`, iOS `Localizable.strings`,
generated `webApp/.../locales/*.json`) are detected only to populate the
`generation.outputs` section — never read as source-of-truth.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from engine.inventory._walk_cache import walk_project
from engine.utils.paths import inventory_dir
from engine.utils.yaml_io import read_yaml, write_yaml

_SCHEMA_VERSION = 1

_PRIMARY_LOCALE_CANDIDATES = ("pt-BR", "pt_BR", "pt", "en-US", "en_US", "en")

_SOT_PATH_CANDIDATES = (
    "shared/resources/i18n",
    "shared/i18n",
    "resources/i18n",
    "i18n",
)

_GENERATED_GLOBS = (
    "**/res/values*/strings.xml",
    "**/*.lproj/Localizable.strings",
    "**/locales/*.json",
)

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

_LOCALE_FILE_RE = re.compile(r"^([a-z]{2,3}(?:[-_][A-Z]{2,4})?)\.json$")
_KEY_SEGMENT_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")


@dataclass
class I18nKey:
    key: str
    languages: dict[str, str] = field(default_factory=dict)
    sources: list[str] = field(default_factory=list)


@dataclass
class I18nInventory:
    keys: list[I18nKey] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    source_of_truth: str = "unknown"
    generated_paths: dict[str, list[str]] = field(default_factory=dict)
    raw: dict = field(default_factory=dict)


def _should_skip(path: Path) -> bool:
    return any(part in _SKIP_DIR_PARTS for part in path.parts)


def _flatten(prefix: str, value: Any, out: dict[str, str]) -> None:
    if isinstance(value, dict):
        for k, v in value.items():
            key = f"{prefix}.{k}" if prefix else k
            _flatten(key, v, out)
    elif isinstance(value, list):
        for i, v in enumerate(value):
            key = f"{prefix}[{i}]"
            _flatten(key, v, out)
    else:
        out[prefix] = "" if value is None else str(value)


def _detect_source_of_truth(project_root: Path) -> Optional[Path]:
    for candidate in _SOT_PATH_CANDIDATES:
        path = project_root / candidate
        if path.is_dir():
            json_files = [
                p for p in path.rglob("*.json") if not _should_skip(p.relative_to(project_root))
            ]
            if json_files:
                return path
    return None


def _collect_locale_files(sot: Path) -> dict[str, list[Path]]:
    by_locale: dict[str, list[Path]] = defaultdict(list)
    for path in sorted(sot.rglob("*.json")):
        match = _LOCALE_FILE_RE.match(path.name)
        if not match:
            continue
        locale = match.group(1).replace("_", "-")
        by_locale[locale].append(path)
    return dict(sorted(by_locale.items()))


def _read_json_safe(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _pick_primary_locale(locales: list[str]) -> str:
    for cand in _PRIMARY_LOCALE_CANDIDATES:
        if cand in locales:
            return cand
    return locales[0] if locales else "unknown"


def _detect_generated_outputs(project_root: Path) -> dict[str, list[str]]:
    # Usa walk cache compartilhado para .xml/.strings; pasta `locales` ainda via rglob
    # (cache é keyed por suffix, não por nome de diretório).
    outputs: dict[str, list[str]] = {"android": [], "ios": [], "web": []}
    xml_paths = walk_project(str(project_root), (".xml",))
    for path in xml_paths:
        if path.name != "strings.xml":
            continue
        rel = path.relative_to(project_root)
        if "/res/values" in str(rel):
            outputs["android"].append(str(rel))
    strings_paths = walk_project(str(project_root), (".strings",))
    for path in strings_paths:
        if path.name != "Localizable.strings":
            continue
        rel = path.relative_to(project_root)
        outputs["ios"].append(str(rel))
    for path in project_root.rglob("locales"):
        rel = path.relative_to(project_root)
        if _should_skip(rel) or not path.is_dir():
            continue
        if "/webApp/" in str(rel) or "/web/" in str(rel):
            outputs["web"].append(str(rel))
    return {k: sorted(v)[:5] for k, v in outputs.items() if v}


def _detect_scripts(project_root: Path) -> tuple[Optional[Path], Optional[Path]]:
    generate = project_root / "scripts" / "i18n" / "generate.py"
    verify = project_root / "scripts" / "i18n" / "verify.py"
    return (generate if generate.exists() else None, verify if verify.exists() else None)


def _naming_pattern(keys: list[str]) -> dict[str, Any]:
    samples = [k for k in keys if "." in k][:10]
    return {
        "pattern": "feature.section.element[.modifier]",
        "examples": samples[:3],
    }


def _keys_by_feature(keys: list[I18nKey]) -> dict[str, dict[str, Any]]:
    by_feature: dict[str, list[str]] = defaultdict(list)
    for k in keys:
        head = k.key.split(".", 1)[0] if "." in k.key else "common"
        by_feature[head].append(k.key)
    result: dict[str, dict[str, Any]] = {}
    for feature, fkeys in sorted(by_feature.items()):
        result[feature] = {
            "count": len(fkeys),
            "keys-sample": sorted(fkeys)[:5],
        }
    return result


def extract_i18n(project_root: Path) -> I18nInventory:
    """Walk the project, detect SoT for i18n, build per-key inventory."""
    sot_path = _detect_source_of_truth(project_root)
    if sot_path is None:
        raw = {
            "schema-version": _SCHEMA_VERSION,
            "last-scan": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source-of-truth": {"path": "unknown", "format": "unknown", "locales": [], "primary-locale": "unknown"},
            "generation": {},
            "verification": {},
            "naming": {},
            "stats": {"total-keys": 0, "by-locale": {}, "parity": 0.0, "missing-translations": []},
            "keys-by-feature": {},
            "orphan-keys": [],
            "hardcoded-detected": [],
        }
        return I18nInventory(raw=raw)

    by_locale = _collect_locale_files(sot_path)
    locales = sorted(by_locale.keys())
    primary = _pick_primary_locale(locales)

    keys_acc: dict[str, I18nKey] = {}
    for locale, files in by_locale.items():
        for f in files:
            data = _read_json_safe(f)
            flat: dict[str, str] = {}
            _flatten("", data, flat)
            rel = str(f.relative_to(project_root))
            for k, v in flat.items():
                entry = keys_acc.get(k)
                if entry is None:
                    entry = I18nKey(key=k)
                    keys_acc[k] = entry
                entry.languages[locale] = v
                if rel not in entry.sources:
                    entry.sources.append(rel)

    keys_list = sorted(keys_acc.values(), key=lambda x: x.key)

    counts_by_locale = {loc: 0 for loc in locales}
    for entry in keys_list:
        for loc in entry.languages.keys():
            counts_by_locale[loc] = counts_by_locale.get(loc, 0) + 1

    total = len(keys_list)
    parity = 1.0
    missing: list[dict[str, Any]] = []
    if total and locales:
        worst = min(counts_by_locale.values()) if counts_by_locale else 0
        parity = round(worst / total, 4) if total else 0.0
        for entry in keys_list:
            missing_locales = [loc for loc in locales if loc not in entry.languages]
            if missing_locales:
                missing.append({"key": entry.key, "missing-locales": missing_locales})

    generated_paths = _detect_generated_outputs(project_root)
    generate_script, verify_script = _detect_scripts(project_root)

    raw = {
        "schema-version": _SCHEMA_VERSION,
        "last-scan": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source-of-truth": {
            "path": str(sot_path.relative_to(project_root)),
            "format": "json-per-locale",
            "locales": locales,
            "primary-locale": primary,
        },
        "generation": {
            "script": str(generate_script.relative_to(project_root)) if generate_script else None,
            "outputs": generated_paths,
        },
        "verification": {
            "script": str(verify_script.relative_to(project_root)) if verify_script else None,
            "checks": ["no-orphan-keys", "all-locales-complete", "naming-consistent"],
        },
        "naming": _naming_pattern([k.key for k in keys_list]),
        "stats": {
            "total-keys": total,
            "by-locale": counts_by_locale,
            "parity": parity,
            "missing-translations": missing[:20],
        },
        "keys-by-feature": _keys_by_feature(keys_list),
        "orphan-keys": [],
        "hardcoded-detected": [],
    }

    return I18nInventory(
        keys=keys_list,
        languages=locales,
        source_of_truth=str(sot_path.relative_to(project_root)),
        generated_paths=generated_paths,
        raw=raw,
    )


def write_i18n_inventory(project_root: Path, inv: I18nInventory) -> Path:
    out = inventory_dir(project_root) / "i18n.yaml"
    write_yaml(out, inv.raw, atomic=True)
    return out


def read_i18n_inventory(project_root: Path) -> Optional[I18nInventory]:
    path = inventory_dir(project_root) / "i18n.yaml"
    if not path.exists():
        return None
    raw = read_yaml(path) or {}
    sot = raw.get("source-of-truth") or {}
    return I18nInventory(
        keys=[],
        languages=list(sot.get("locales") or []),
        source_of_truth=sot.get("path", "unknown"),
        generated_paths=dict((raw.get("generation") or {}).get("outputs") or {}),
        raw=raw,
    )
