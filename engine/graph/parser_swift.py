"""Pragmatic regex-based Swift parser.

Extracts imports, top-level types, SwiftUI view detection, @StateObject /
@ObservedObject / @Published property wrappers, accessibility identifiers,
NSLocalizedString keys — **and** reuse-intelligence metadata for funcs:
visibility, signature, extension receiver type, body hash + tokens, modifiers.

Two-pass for extensions:
  1. Scan `extension Type { ... }` blocks to find their character ranges.
  2. When emitting func/var declarations, attach the enclosing receiver type.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from engine.graph._body_text import (
    extract_body_tokens,
    extract_function_body,
    hash_body,
    tokens_to_json,
)

_RE_IMPORT = re.compile(r"^\s*import\s+([A-Za-z_][A-Za-z0-9_\.]*)", re.MULTILINE)

# Type-level declarations (existing — captures `extension`, `struct`, etc.)
_RE_TYPE_DECL = re.compile(
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

# Func declarations. Capture visibility + modifiers; ``async``/``throws`` are
# Swift-only modifiers that influence call sites.
_FUNC_MODIFIERS = (
    "static",
    "class",
    "final",
    "override",
    "mutating",
    "nonmutating",
    "async",
    "throws",
    "rethrows",
    "convenience",
    "required",
    "lazy",
    "weak",
    "unowned",
)

_RE_FUNC_DECL = re.compile(
    r"""
    ^(?P<indent>[ \t]*)
    (?:(?P<visibility>public|internal|private|fileprivate|open)\s+)?
    (?P<modifiers>(?:(?:%s)\s+)*)
    func\s+
    (?P<name>[A-Za-z_][A-Za-z0-9_]*)
    """ % "|".join(sorted(set(_FUNC_MODIFIERS), key=len, reverse=True)),
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
    is_view: bool = False
    is_observable: bool = False
    property_wrappers: tuple[str, ...] = field(default_factory=tuple)
    visibility: str = "internal"
    signature: Optional[str] = None
    receiver_type: Optional[str] = None
    body_hash: Optional[str] = None
    body_tokens: Optional[str] = None
    modifiers: tuple[str, ...] = field(default_factory=tuple)


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

    extension_ranges = _find_extension_ranges(text)

    symbols: list[SwiftSymbol] = []
    for match in _RE_TYPE_DECL.finditer(text):
        kind = match.group("kind")
        name = match.group("name")
        conforms = match.group("conforms") or ""
        line_no = text.count("\n", 0, match.start()) + 1
        visibility = (match.group("visibility") or "internal").strip()

        is_view = bool(_RE_VIEW_CONFORMANCE.search(conforms))
        is_observable = bool(_RE_OBSERVABLE_CONFORMANCE.search(conforms))

        window_end = match.end() + 600
        window = text[match.end():window_end]
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
                visibility=visibility,
            )
        )

    for match in _RE_FUNC_DECL.finditer(text):
        name = match.group("name")
        line_no = text.count("\n", 0, match.start()) + 1
        visibility = (match.group("visibility") or "internal").strip()
        modifiers_str = match.group("modifiers") or ""
        modifiers = tuple(m for m in modifiers_str.split() if m)
        receiver = _enclosing_extension(extension_ranges, match.start())

        signature, body_text = _parse_swift_function_tail(text, match.end(), receiver)
        body_hash = hash_body(body_text) if body_text is not None else None
        tokens_json: Optional[str] = None
        if body_text is not None:
            tokens = extract_body_tokens(body_text, language="swift")
            tokens_json = tokens_to_json(tokens) if tokens else None

        symbols.append(
            SwiftSymbol(
                file_path=str(path),
                name=name,
                kind="func",
                line=line_no,
                visibility=visibility,
                signature=signature,
                receiver_type=receiver,
                body_hash=body_hash,
                body_tokens=tokens_json,
                modifiers=modifiers,
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


_RE_EXTENSION_HEADER = re.compile(
    r"""
    ^(?P<indent>[ \t]*)
    (?:(?:public|internal|private|fileprivate|open)\s+)?
    extension\s+
    (?P<name>[A-Za-z_][A-Za-z0-9_\.]*)
    (?:\s*<[^>]+>)?
    (?:\s*:\s*[^{]+?)?
    \s*\{
    """,
    re.MULTILINE | re.VERBOSE,
)


def _find_extension_ranges(text: str) -> list[tuple[str, int, int]]:
    """Locate each ``extension Type { ... }`` block; return ``(type, start, end)``.

    ``start`` is the offset of the opening ``{``, ``end`` of the matching ``}``.
    Nested extensions / inner braces are respected.
    """
    ranges: list[tuple[str, int, int]] = []
    for match in _RE_EXTENSION_HEADER.finditer(text):
        type_name = match.group("name")
        brace_offset = match.end() - 1
        if brace_offset < 0 or brace_offset >= len(text) or text[brace_offset] != "{":
            continue
        close_offset = _scan_matching_brace(text, brace_offset)
        if close_offset is None:
            continue
        ranges.append((type_name, brace_offset, close_offset))
    return ranges


def _enclosing_extension(
    ranges: list[tuple[str, int, int]],
    pos: int,
) -> Optional[str]:
    """Return the receiver type if ``pos`` falls inside an extension block.

    Innermost match wins (handles nested extension blocks).
    """
    candidates = [r for r in ranges if r[1] < pos < r[2]]
    if not candidates:
        return None
    candidates.sort(key=lambda r: r[2] - r[1])
    return candidates[0][0]


def _scan_matching_brace(source: str, open_offset: int) -> Optional[int]:
    """Find the `}` matching the `{` at ``open_offset``, respecting strings/comments."""
    if source[open_offset] != "{":
        return None
    depth = 1
    i = open_offset + 1
    n = len(source)
    in_line_comment = False
    in_block_comment = False
    in_string_double = False
    in_string_single = False
    in_string_multiline = False

    while i < n and depth > 0:
        ch = source[i]
        nxt = source[i + 1] if i + 1 < n else ""

        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue
        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue
        if in_string_multiline:
            if source[i:i + 3] == '"""':
                in_string_multiline = False
                i += 3
                continue
            i += 1
            continue
        if in_string_double:
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                in_string_double = False
            i += 1
            continue
        if in_string_single:
            if ch == "\\":
                i += 2
                continue
            if ch == "'":
                in_string_single = False
            i += 1
            continue

        if ch == "/" and nxt == "/":
            in_line_comment = True
            i += 2
            continue
        if ch == "/" and nxt == "*":
            in_block_comment = True
            i += 2
            continue
        if source[i:i + 3] == '"""':
            in_string_multiline = True
            i += 3
            continue
        if ch == '"':
            in_string_double = True
            i += 1
            continue
        if ch == "'":
            in_string_single = True
            i += 1
            continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return None


def _parse_swift_function_tail(
    source: str,
    decl_end_offset: int,
    receiver: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    """Walk past the func name to extract signature + body."""
    n = len(source)
    i = decl_end_offset

    if i < n and source[i] == "<":
        depth = 1
        i += 1
        while i < n and depth > 0:
            if source[i] == "<":
                depth += 1
            elif source[i] == ">":
                depth -= 1
            i += 1

    while i < n and source[i].isspace():
        i += 1

    if i >= n or source[i] != "(":
        return None, None

    params_start = i
    params_end = _scan_matching_paren(source, params_start)
    if params_end is None:
        return None, None
    params_text = source[params_start + 1:params_end]

    i = params_end + 1
    effects: list[str] = []
    while i < n:
        while i < n and source[i].isspace():
            i += 1
        rest = source[i:i + 16]
        if rest.startswith("async"):
            effects.append("async")
            i += 5
            continue
        if rest.startswith("throws"):
            effects.append("throws")
            i += 6
            continue
        if rest.startswith("rethrows"):
            effects.append("rethrows")
            i += 8
            continue
        break

    return_type: Optional[str] = None
    if i < n - 1 and source[i:i + 2] == "->":
        i += 2
        while i < n and source[i].isspace():
            i += 1
        return_start = i
        return_end = _find_swift_return_type_end(source, return_start)
        return_type = source[return_start:return_end].strip() or None
        i = return_end

    while i < n and source[i].isspace():
        i += 1

    body_text: Optional[str] = None
    if i < n and source[i] == "{":
        body_text = extract_function_body(source, i, language="swift")

    signature = _normalize_swift_signature(params_text, return_type, receiver, effects)
    return signature, body_text


def _find_swift_return_type_end(source: str, start: int) -> int:
    n = len(source)
    depth_angle = 0
    i = start
    while i < n:
        ch = source[i]
        if ch == "<":
            depth_angle += 1
        elif ch == ">":
            if depth_angle > 0:
                depth_angle -= 1
        elif depth_angle == 0:
            if ch in "{\n":
                return i
            if ch == "w" and source[i:i + 6] == "where ":
                return i
        i += 1
    return n


def _scan_matching_paren(source: str, open_offset: int) -> Optional[int]:
    if source[open_offset] != "(":
        return None
    depth = 1
    i = open_offset + 1
    n = len(source)
    in_string_double = False
    while i < n and depth > 0:
        ch = source[i]
        if in_string_double:
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                in_string_double = False
            i += 1
            continue
        if ch == '"':
            in_string_double = True
            i += 1
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return None


def _normalize_swift_signature(
    params_text: str,
    return_type: Optional[str],
    receiver: Optional[str],
    effects: list[str],
) -> str:
    """Strip parameter labels + names, keep types.

    Swift params look like ``label name: Type = default`` or ``name: Type``.
    Canonical form keeps only types, comma-separated. Effects appear after
    the param list as ``async throws`` etc.
    """
    param_types = _strip_swift_param_labels(params_text)
    head = f"{receiver}.func" if receiver else "func"
    body = f"({param_types})"
    effects_str = (" " + " ".join(effects)) if effects else ""
    tail = f" -> {return_type.strip()}" if return_type else ""
    return f"{head}{body}{effects_str}{tail}"


def _strip_swift_param_labels(params_text: str) -> str:
    text = (params_text or "").strip()
    if not text:
        return ""
    parts = _split_swift_params(text)
    out: list[str] = []
    for part in parts:
        cleaned = part.strip()
        if not cleaned:
            continue
        cleaned = re.sub(r"^@\w+\s+", "", cleaned)
        cleaned = re.sub(r"^inout\s+", "", cleaned)
        colon_idx = _find_top_level_colon(cleaned)
        if colon_idx < 0:
            out.append(cleaned)
            continue
        type_part = cleaned[colon_idx + 1:].strip()
        type_part = type_part.split("=", 1)[0].strip()
        out.append(type_part)
    return ", ".join(out)


def _split_swift_params(text: str) -> list[str]:
    depth = 0
    last = 0
    parts: list[str] = []
    for i, ch in enumerate(text):
        if ch in "<([":
            depth += 1
        elif ch in ">)]":
            if depth > 0:
                depth -= 1
        elif ch == "," and depth == 0:
            parts.append(text[last:i])
            last = i + 1
    parts.append(text[last:])
    return parts


def _find_top_level_colon(text: str) -> int:
    depth = 0
    for i, ch in enumerate(text):
        if ch in "<([":
            depth += 1
        elif ch in ">)]":
            if depth > 0:
                depth -= 1
        elif ch == ":" and depth == 0:
            return i
    return -1


__all__ = [
    "SwiftSymbol",
    "SwiftFileInfo",
    "parse_swift_file",
]
