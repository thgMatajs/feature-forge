"""Pragmatic regex-based Kotlin parser.

Extracts package, imports, top-level symbols, DI annotations, i18n keys, and
test tags. Not an AST — best-effort, downstream validators tolerate false
positives. Switch to tree-sitter for v2 if accuracy bites.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

_RE_PACKAGE = re.compile(r"^\s*package\s+([\w\.]+)", re.MULTILINE)
_RE_IMPORT = re.compile(r"^\s*import\s+([\w\.\*]+)(?:\s+as\s+\w+)?\s*$", re.MULTILINE)

# Top-level declarations. Capture visibility + annotations preceding the kind.
_RE_DECL = re.compile(
    r"""
    ^(?P<indent>[ \t]*)
    (?:(?P<visibility>public|private|internal|protected)\s+)?
    (?:(?P<modifier>open|abstract|final|sealed|data|inline|inner|enum|annotation|companion|value)\s+)?
    (?:(?P<modifier2>open|abstract|final|sealed|data|inline|inner|enum|annotation|companion|value)\s+)?
    (?P<kind>class|object|interface|fun|val|var)\s+
    (?:<[^>]+>\s+)?
    (?P<name>[A-Za-z_][A-Za-z0-9_]*)
    """,
    re.MULTILINE | re.VERBOSE,
)

_RE_ANNOTATION = re.compile(r"@([A-Z][A-Za-z0-9_]*)(?:\(([^)]*)\))?")

_KOIN_ANNOTATIONS = {"Single", "Factory", "KoinViewModel", "Module", "ComponentScan", "Scope", "Scoped"}
_COMPOSABLE_ANNOTATION = "Composable"

# i18n usage — stringResource(R.string.X) ou helpers como i18n("a.b.c") / strings.X
_RE_STRING_RESOURCE = re.compile(r"stringResource\(\s*R\.string\.([A-Za-z_][A-Za-z0-9_]*)\s*[\),]")
_RE_I18N_HELPER = re.compile(r"""i18n\(\s*["']([^"']+)["']""")

# Test tags — Modifier.testTag("literal") OR Modifier.testTag(AuthTestIds.X.Y)
_RE_TEST_TAG_LITERAL = re.compile(r"""testTag\(\s*["']([^"']+)["']\s*\)""")
_RE_TEST_TAG_REF = re.compile(r"testTag\(\s*([A-Z][A-Za-z0-9_\.]+)\s*\)")

# Firebase markers (best-effort; populates `imports` table indirectly via raw refs)
_RE_FIREBASE = re.compile(
    r"\b(Firebase(?:Firestore|Auth|Storage|Messaging|Crashlytics|Analytics|App)?"
    r"|FirebaseAuth\b|FirebaseFirestore\b)\b"
)


@dataclass(frozen=True)
class KotlinSymbol:
    file_path: str
    package: str
    name: str
    kind: str
    line: int
    annotations: tuple[str, ...]
    parent_class: Optional[str]


@dataclass
class KotlinFileInfo:
    file_path: str
    package: str
    imports: list[str] = field(default_factory=list)
    symbols: list[KotlinSymbol] = field(default_factory=list)
    i18n_keys_used: list[str] = field(default_factory=list)
    test_tags_used: list[str] = field(default_factory=list)
    di_annotations: list[dict] = field(default_factory=list)
    firebase_refs: list[str] = field(default_factory=list)


def parse_kotlin_file(path: Path) -> KotlinFileInfo:
    """Parse a single .kt file. Returns a populated KotlinFileInfo."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return KotlinFileInfo(file_path=str(path), package="")

    package_match = _RE_PACKAGE.search(text)
    package = package_match.group(1) if package_match else ""

    imports = sorted({m.group(1) for m in _RE_IMPORT.finditer(text)})

    symbols: list[KotlinSymbol] = []
    di_annotations: list[dict] = []
    lines = text.splitlines()

    for match in _RE_DECL.finditer(text):
        kind = match.group("kind")
        name = match.group("name")
        if not name:
            continue
        line_no = text.count("\n", 0, match.start()) + 1
        ann_block = _annotations_before(lines, line_no - 1)
        annotations = tuple(_extract_annotation_names(ann_block))
        is_top_level = (match.group("indent") or "") == ""

        symbols.append(
            KotlinSymbol(
                file_path=str(path),
                package=package,
                name=name,
                kind=_normalize_kind(kind, match.group("modifier"), match.group("modifier2"), annotations),
                line=line_no,
                annotations=annotations,
                parent_class=None if is_top_level else _enclosing_class(lines, line_no - 1),
            )
        )

        for ann in annotations:
            if ann in _KOIN_ANNOTATIONS:
                di_annotations.append({"kind": kind, "annotation": ann, "class_name": name})

    i18n_keys = sorted(
        {m.group(1) for m in _RE_STRING_RESOURCE.finditer(text)}
        | {m.group(1) for m in _RE_I18N_HELPER.finditer(text)}
    )
    test_tags = sorted(
        {m.group(1) for m in _RE_TEST_TAG_LITERAL.finditer(text)}
        | {m.group(1) for m in _RE_TEST_TAG_REF.finditer(text)}
    )
    firebase_refs = sorted({m.group(1) for m in _RE_FIREBASE.finditer(text)})

    return KotlinFileInfo(
        file_path=str(path),
        package=package,
        imports=imports,
        symbols=symbols,
        i18n_keys_used=i18n_keys,
        test_tags_used=test_tags,
        di_annotations=di_annotations,
        firebase_refs=firebase_refs,
    )


def _annotations_before(lines: list[str], idx: int) -> str:
    """Collect annotation lines immediately above the declaration."""
    collected: list[str] = []
    cursor = idx - 1
    while cursor >= 0:
        stripped = lines[cursor].strip()
        if not stripped:
            cursor -= 1
            continue
        if stripped.startswith("@") or stripped.startswith(")"):
            collected.append(stripped)
            cursor -= 1
            continue
        break
    return "\n".join(reversed(collected))


def _extract_annotation_names(block: str) -> list[str]:
    return [m.group(1) for m in _RE_ANNOTATION.finditer(block)]


def _normalize_kind(kind: str, mod1: Optional[str], mod2: Optional[str], annotations: tuple[str, ...]) -> str:
    if kind == "class":
        if (mod1 == "sealed") or (mod2 == "sealed"):
            return "sealed_class"
        if (mod1 == "enum") or (mod2 == "enum"):
            return "enum"
        if (mod1 == "data") or (mod2 == "data"):
            return "data_class"
        return "class"
    if kind == "fun" and _COMPOSABLE_ANNOTATION in annotations:
        return "composable_fun"
    return kind


def _enclosing_class(lines: list[str], idx: int) -> Optional[str]:
    """Walk upward to find the nearest enclosing class/object/interface."""
    pattern = re.compile(
        r"^\s*(?:public|private|internal|protected)?\s*"
        r"(?:sealed|data|enum|inner|abstract|open|final)?\s*"
        r"(?:class|object|interface)\s+([A-Za-z_][A-Za-z0-9_]*)"
    )
    cursor = idx - 1
    while cursor >= 0:
        match = pattern.match(lines[cursor])
        if match:
            return match.group(1)
        cursor -= 1
    return None
