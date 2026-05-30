"""Pragmatic regex-based Swift parser.

Extracts imports, top-level types, SwiftUI view detection, @StateObject /
@ObservedObject / @Published property wrappers, accessibility identifiers,
and NSLocalizedString keys. Best-effort.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

_RE_IMPORT = re.compile(r"^\s*import\s+([A-Za-z_][A-Za-z0-9_\.]*)", re.MULTILINE)

_RE_DECL = re.compile(
    r"""
    ^(?P<indent>[ \t]*)
    (?:(?P<visibility>public|internal|private|fileprivate|open)\s+)?
    (?:(?P<modifier>final|indirect|@MainActor|@objc)\s+)?
    (?P<kind>struct|class|enum|protocol|extension|actor)\s+
    (?P<name>[A-Za-z_][A-Za-z0-9_]*)
    (?:\s*<[^>]+>)?
    (?:\s*:\s*(?P<conforms>[^{]+?))?
    \s*\{
    """,
    re.MULTILINE | re.VERBOSE,
)

_RE_PROPERTY_WRAPPER = re.compile(
    r"@(StateObject|ObservedObject|Published|EnvironmentObject|State|Binding)\b"
)

_RE_ACCESSIBILITY_ID = re.compile(
    r"""\.accessibilityIdentifier\(\s*["']([^"']+)["']\s*\)"""
)
_RE_ACCESSIBILITY_ID_REF = re.compile(
    r"\.accessibilityIdentifier\(\s*([A-Z][A-Za-z0-9_\.]+(?:\.shared)?\.[A-Z0-9_]+)\s*\)"
)

_RE_NSLOCALIZED = re.compile(
    r"""NSLocalizedString\(\s*["']([^"']+)["']"""
)
_RE_I18N_HELPER = re.compile(
    r"""(?:Strings|L10n)\.([A-Za-z_][A-Za-z0-9_\.]*)"""
)

_RE_VIEW_CONFORMANCE = re.compile(r"\bView\b")
_RE_OBSERVABLE_CONFORMANCE = re.compile(r"\bObservableObject\b")


@dataclass(frozen=True)
class SwiftSymbol:
    file_path: str
    name: str
    kind: str
    line: int
    is_view: bool
    is_observable: bool
    property_wrappers: tuple[str, ...]


@dataclass
class SwiftFileInfo:
    file_path: str
    imports: list[str] = field(default_factory=list)
    symbols: list[SwiftSymbol] = field(default_factory=list)
    i18n_keys_used: list[str] = field(default_factory=list)
    accessibility_ids: list[str] = field(default_factory=list)
    property_wrappers: list[str] = field(default_factory=list)


def parse_swift_file(path: Path) -> SwiftFileInfo:
    """Parse a single .swift file."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return SwiftFileInfo(file_path=str(path))

    imports = sorted({m.group(1) for m in _RE_IMPORT.finditer(text)})

    symbols: list[SwiftSymbol] = []
    for match in _RE_DECL.finditer(text):
        kind = match.group("kind")
        name = match.group("name")
        conforms = match.group("conforms") or ""
        line_no = text.count("\n", 0, match.start()) + 1

        is_view = bool(_RE_VIEW_CONFORMANCE.search(conforms))
        is_observable = bool(_RE_OBSERVABLE_CONFORMANCE.search(conforms))

        # Scan a small window after the decl for property wrappers it owns.
        window_end = match.end() + 600
        window = text[match.end() : window_end]
        wrappers = tuple(sorted({m.group(1) for m in _RE_PROPERTY_WRAPPER.finditer(window)}))

        symbols.append(
            SwiftSymbol(
                file_path=str(path),
                name=name,
                kind=kind,
                line=line_no,
                is_view=is_view,
                is_observable=is_observable,
                property_wrappers=wrappers,
            )
        )

    i18n_keys = sorted(
        {m.group(1) for m in _RE_NSLOCALIZED.finditer(text)}
        | {m.group(1) for m in _RE_I18N_HELPER.finditer(text)}
    )
    a11y_ids = sorted(
        {m.group(1) for m in _RE_ACCESSIBILITY_ID.finditer(text)}
        | {m.group(1) for m in _RE_ACCESSIBILITY_ID_REF.finditer(text)}
    )
    wrappers_global = sorted({m.group(1) for m in _RE_PROPERTY_WRAPPER.finditer(text)})

    return SwiftFileInfo(
        file_path=str(path),
        imports=imports,
        symbols=symbols,
        i18n_keys_used=i18n_keys,
        accessibility_ids=a11y_ids,
        property_wrappers=wrappers_global,
    )
