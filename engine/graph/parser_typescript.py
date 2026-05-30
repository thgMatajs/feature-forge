"""Pragmatic regex-based TypeScript/TSX parser.

Extracts ES module imports, named exports, React functional components,
Tailwind class strings (rough heuristic), i18n translation calls and
data-testid attributes. Best-effort — no AST.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_RE_IMPORT = re.compile(
    r"""^\s*import\s+(?:type\s+)?(?:[^"']+?)\s+from\s+["']([^"']+)["']""",
    re.MULTILINE,
)
_RE_IMPORT_BARE = re.compile(r"""^\s*import\s+["']([^"']+)["']""", re.MULTILINE)

_RE_EXPORT_CONST = re.compile(
    r"""^\s*export\s+(?:const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)""",
    re.MULTILINE,
)
_RE_EXPORT_FUNC = re.compile(
    r"""^\s*export\s+(?:default\s+)?(?:async\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)""",
    re.MULTILINE,
)
_RE_EXPORT_CLASS = re.compile(
    r"""^\s*export\s+(?:default\s+)?(?:abstract\s+)?class\s+([A-Za-z_][A-Za-z0-9_]*)""",
    re.MULTILINE,
)
_RE_EXPORT_TYPE = re.compile(
    r"""^\s*export\s+(?:type|interface|enum)\s+([A-Za-z_][A-Za-z0-9_]*)""",
    re.MULTILINE,
)
_RE_EXPORT_DEFAULT_ANON = re.compile(r"""^\s*export\s+default\s+(?!function|class)""", re.MULTILINE)

# React functional components — must start with capital letter.
_RE_RFC_ARROW = re.compile(
    r"""(?:^|\n)(?:export\s+(?:default\s+)?)?const\s+(?P<name>[A-Z][A-Za-z0-9_]*)\s*"""
    r"""(?::\s*[^=]+)?=\s*(?:\([^)]*\)|[A-Za-z_][A-Za-z0-9_]*)\s*=>\s*[\(\{]""",
)
_RE_RFC_FUNC = re.compile(
    r"""(?:^|\n)(?:export\s+(?:default\s+)?)?function\s+(?P<name>[A-Z][A-Za-z0-9_]*)\s*\("""
)

_RE_DATA_TESTID = re.compile(r"""data-testid=\s*["'`]([^"'`]+)["'`]""")
_RE_DATA_TESTID_EXPR = re.compile(r"""data-testid=\s*\{\s*([A-Za-z_][A-Za-z0-9_\.]*)\s*\}""")

_RE_T_CALL = re.compile(r"""\bt\(\s*["'`]([^"'`]+)["'`]""")
_RE_USE_TRANSLATION = re.compile(r"\buseTranslation\(")

# Tailwind: capture `className="..."` strings — heuristic only.
_RE_CLASSNAME = re.compile(r"""className=\s*["'`]([^"'`]+)["'`]""")


@dataclass(frozen=True)
class TypeScriptSymbol:
    file_path: str
    name: str
    kind: str
    line: int


@dataclass
class TypeScriptFileInfo:
    file_path: str
    imports: list[str] = field(default_factory=list)
    symbols: list[TypeScriptSymbol] = field(default_factory=list)
    components: list[str] = field(default_factory=list)
    i18n_keys_used: list[str] = field(default_factory=list)
    test_ids: list[str] = field(default_factory=list)
    tailwind_classes: list[str] = field(default_factory=list)
    uses_translation_hook: bool = False


def parse_typescript_file(path: Path) -> TypeScriptFileInfo:
    """Parse a single .ts / .tsx / .js / .jsx file."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return TypeScriptFileInfo(file_path=str(path))

    imports = sorted(
        {m.group(1) for m in _RE_IMPORT.finditer(text)}
        | {m.group(1) for m in _RE_IMPORT_BARE.finditer(text)}
    )

    symbols: list[TypeScriptSymbol] = []
    for kind, pattern in (
        ("const", _RE_EXPORT_CONST),
        ("function", _RE_EXPORT_FUNC),
        ("class", _RE_EXPORT_CLASS),
        ("type", _RE_EXPORT_TYPE),
    ):
        for match in pattern.finditer(text):
            line_no = text.count("\n", 0, match.start()) + 1
            symbols.append(
                TypeScriptSymbol(
                    file_path=str(path),
                    name=match.group(1),
                    kind=kind,
                    line=line_no,
                )
            )

    components_set: set[str] = set()
    for pattern in (_RE_RFC_ARROW, _RE_RFC_FUNC):
        for match in pattern.finditer(text):
            components_set.add(match.group("name"))
    components = sorted(components_set)

    test_ids = sorted(
        {m.group(1) for m in _RE_DATA_TESTID.finditer(text)}
        | {m.group(1) for m in _RE_DATA_TESTID_EXPR.finditer(text)}
    )
    i18n_keys = sorted({m.group(1) for m in _RE_T_CALL.finditer(text)})

    classnames: set[str] = set()
    for match in _RE_CLASSNAME.finditer(text):
        for token in match.group(1).split():
            token = token.strip()
            if token:
                classnames.add(token)
    tailwind_classes = sorted(classnames)

    return TypeScriptFileInfo(
        file_path=str(path),
        imports=imports,
        symbols=symbols,
        components=components,
        i18n_keys_used=i18n_keys,
        test_ids=test_ids,
        tailwind_classes=tailwind_classes,
        uses_translation_hook=bool(_RE_USE_TRANSLATION.search(text)),
    )
