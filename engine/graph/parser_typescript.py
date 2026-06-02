"""Pragmatic regex-based TypeScript/TSX parser.

Extracts ES module imports, named exports, React functional components,
Tailwind class strings (rough heuristic), i18n translation calls and
data-testid attributes. Best-effort — no AST.

Reuse-intelligence additions:
- visibility (derived from ``export`` prefix)
- signature (param types, return type)
- body_hash + body_tokens for top-level functions
- modifiers (``async``, ``function*``)

NO ``receiver_type`` — TS has no extension methods in v1.
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
    r"""^\s*export\s+(?:default\s+)?(?:async\s+)?function(?P<gen>\*)?\s+([A-Za-z_][A-Za-z0-9_]*)""",
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

# One-level balanced-paren match for the parameter list: ``(`` then any
# sequence of (non-paren chars OR a one-level nested ``(...)``) then ``)``.
# Catches destructured props with arrow defaults like
# ``({callback = (x) => x})`` — see R2.6. Depth-2 nesting (defaults
# containing destructured defaults) is rare enough to not justify a full
# bracket matcher.
#
# Body lookahead accepts ``(`` (parenthesized expression), ``{`` (block or
# object), or ``<`` (JSX element / fragment / generic-call) — all three
# are common RFC body starts.
_RE_RFC_ARROW = re.compile(
    r"""(?:^|\n)(?:export\s+(?:default\s+)?)?const\s+(?P<name>[A-Z][A-Za-z0-9_]*)\s*"""
    r"""(?::\s*[^=]+)?=\s*"""
    r"""(?:\((?:[^()]|\([^()]*\))*\)|[A-Za-z_][A-Za-z0-9_]*)\s*=>\s*[\(\{<]""",
)
_RE_RFC_FUNC = re.compile(
    r"""(?:^|\n)(?:export\s+(?:default\s+)?)?function\s+(?P<name>[A-Z][A-Za-z0-9_]*)\s*\("""
)

# Top-level function declarations (with or without export, including async / generator).
_RE_FUNCTION_DECL = re.compile(
    r"""
    ^(?P<indent>[ \t]*)
    (?P<export>export\s+(?:default\s+)?)?
    (?P<async>async\s+)?
    function(?P<gen>\*)?\s+
    (?P<name>[A-Za-z_][A-Za-z0-9_]*)
    """,
    re.MULTILINE | re.VERBOSE,
)

# Arrow function declarations: `const name = (...) => ...` (with optional async).
_RE_ARROW_DECL = re.compile(
    r"""
    ^(?P<indent>[ \t]*)
    (?P<export>export\s+(?:default\s+)?)?
    (?:const|let|var)\s+
    (?P<name>[A-Za-z_][A-Za-z0-9_]*)
    (?:\s*:\s*[^=]+?)?
    \s*=\s*
    (?P<async>async\s+)?
    """,
    re.MULTILINE | re.VERBOSE,
)

_RE_DATA_TESTID = re.compile(r"""data-testid=\s*["'`]([^"'`]+)["'`]""")
_RE_DATA_TESTID_EXPR = re.compile(r"""data-testid=\s*\{\s*([A-Za-z_][A-Za-z0-9_\.]*)\s*\}""")

_RE_T_CALL = re.compile(r"""\bt\(\s*["'`]([^"'`]+)["'`]""")
_RE_USE_TRANSLATION = re.compile(r"\buseTranslation\(")

_RE_CLASSNAME = re.compile(r"""className=\s*["'`]([^"'`]+)["'`]""")


@dataclass(frozen=True)
class TypeScriptSymbol:
    file_path: str
    name: str
    kind: str
    line: int
    visibility: str = "private"
    signature: Optional[str] = None
    body_hash: Optional[str] = None
    body_tokens: Optional[str] = None
    modifiers: tuple[str, ...] = field(default_factory=tuple)


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
    seen_names: set[tuple[str, str]] = set()

    for match in _RE_FUNCTION_DECL.finditer(text):
        name = match.group("name")
        line_no = text.count("\n", 0, match.start()) + 1
        is_export = bool(match.group("export"))
        is_async = bool(match.group("async"))
        is_generator = match.group("gen") == "*"
        modifiers_list: list[str] = []
        if is_async:
            modifiers_list.append("async")
        if is_generator:
            modifiers_list.append("generator")
        signature, body_text = _parse_ts_function_tail(text, match.end())
        body_hash = hash_body(body_text) if body_text is not None else None
        tokens_json: Optional[str] = None
        if body_text is not None:
            tokens = extract_body_tokens(body_text, language="typescript")
            tokens_json = tokens_to_json(tokens) if tokens else None

        symbols.append(
            TypeScriptSymbol(
                file_path=str(path),
                name=name,
                kind="function",
                line=line_no,
                visibility="public" if is_export else "private",
                signature=signature,
                body_hash=body_hash,
                body_tokens=tokens_json,
                modifiers=tuple(modifiers_list),
            )
        )
        seen_names.add(("function", name))

    for match in _RE_ARROW_DECL.finditer(text):
        name = match.group("name")
        # Dedup early — a same-named `function` declaration above wins.
        # This skips the body extraction + hashing + tokenization cost.
        if ("function", name) in seen_names:
            continue
        line_no = text.count("\n", 0, match.start()) + 1
        is_export = bool(match.group("export"))
        is_async = bool(match.group("async"))
        signature, body_text = _parse_ts_arrow_tail(text, match.end())
        if signature is None and body_text is None:
            continue
        modifiers_list = ["async"] if is_async else []
        body_hash = hash_body(body_text) if body_text is not None else None
        tokens_json2: Optional[str] = None
        if body_text is not None:
            tokens = extract_body_tokens(body_text, language="typescript")
            tokens_json2 = tokens_to_json(tokens) if tokens else None

        symbols.append(
            TypeScriptSymbol(
                file_path=str(path),
                name=name,
                kind="function",
                line=line_no,
                visibility="public" if is_export else "private",
                signature=signature,
                body_hash=body_hash,
                body_tokens=tokens_json2,
                modifiers=tuple(modifiers_list),
            )
        )
        seen_names.add(("function", name))

    for kind_label, pattern in (
        ("const", _RE_EXPORT_CONST),
        ("class", _RE_EXPORT_CLASS),
        ("type", _RE_EXPORT_TYPE),
    ):
        for match in pattern.finditer(text):
            name = match.group(1)
            if (kind_label, name) in seen_names or ("function", name) in seen_names:
                continue
            line_no = text.count("\n", 0, match.start()) + 1
            symbols.append(
                TypeScriptSymbol(
                    file_path=str(path),
                    name=name,
                    kind=kind_label,
                    line=line_no,
                    visibility="public",
                )
            )
            seen_names.add((kind_label, name))

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


def _parse_ts_function_tail(
    source: str,
    decl_end_offset: int,
) -> tuple[Optional[str], Optional[str]]:
    """Capture ``(params): ReturnType { body }`` after a ``function name``."""
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
    while i < n and source[i].isspace():
        i += 1

    return_type: Optional[str] = None
    if i < n and source[i] == ":":
        i += 1
        while i < n and source[i].isspace():
            i += 1
        return_start = i
        return_end = _find_ts_return_type_end(source, return_start)
        return_type = source[return_start:return_end].strip() or None
        i = return_end

    while i < n and source[i].isspace():
        i += 1

    body_text: Optional[str] = None
    if i < n and source[i] == "{":
        body_text = extract_function_body(source, i, language="typescript")

    signature = _normalize_ts_signature(params_text, return_type)
    return signature, body_text


def _parse_ts_arrow_tail(
    source: str,
    decl_end_offset: int,
) -> tuple[Optional[str], Optional[str]]:
    """Capture ``(params): ReturnType => body`` after ``const name = [async]``."""
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

    if i >= n:
        return None, None

    params_text = ""
    if source[i] == "(":
        params_start = i
        params_end = _scan_matching_paren(source, params_start)
        if params_end is None:
            return None, None
        params_text = source[params_start + 1:params_end]
        i = params_end + 1
    elif source[i].isalpha() or source[i] == "_":
        ident_start = i
        while i < n and (source[i].isalnum() or source[i] == "_"):
            i += 1
        params_text = source[ident_start:i]
    else:
        return None, None

    while i < n and source[i].isspace():
        i += 1

    return_type: Optional[str] = None
    if i < n and source[i] == ":":
        i += 1
        while i < n and source[i].isspace():
            i += 1
        return_start = i
        while i < n - 1 and source[i:i + 2] != "=>":
            i += 1
        return_type = source[return_start:i].strip() or None

    while i < n - 1 and source[i:i + 2] != "=>":
        i += 1
    if i >= n - 1:
        return None, None
    i += 2

    while i < n and source[i].isspace():
        i += 1

    body_text: Optional[str] = None
    if i < n and source[i] == "{":
        body_text = extract_function_body(source, i, language="typescript")

    signature = _normalize_ts_signature(params_text, return_type)
    return signature, body_text


def _find_ts_return_type_end(source: str, start: int) -> int:
    """Return-type ends at the function body `{`, an assignment `=` or newline.

    The check fires BEFORE updating depth so the body's opening `{` (which
    arrives at depth 0) terminates the scan instead of being counted.
    """
    n = len(source)
    depth_angle = 0
    depth_paren = 0  # (), [] only — `{` always terminates at depth 0
    i = start
    while i < n:
        ch = source[i]
        if depth_angle == 0 and depth_paren == 0:
            if ch == "{" or ch == "=" or ch == "\n":
                return i
        if ch == "<":
            depth_angle += 1
        elif ch == ">":
            if depth_angle > 0:
                depth_angle -= 1
        elif ch in "([":
            depth_paren += 1
        elif ch in ")]":
            if depth_paren > 0:
                depth_paren -= 1
        i += 1
    return n


def _scan_matching_paren(source: str, open_offset: int) -> Optional[int]:
    if source[open_offset] != "(":
        return None
    depth = 1
    i = open_offset + 1
    n = len(source)
    in_string_double = False
    in_string_single = False
    in_template = False
    template_depth = 0
    while i < n and depth > 0:
        ch = source[i]
        nxt = source[i + 1] if i + 1 < n else ""
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
        if in_template:
            if ch == "\\":
                i += 2
                continue
            if ch == "`":
                in_template = False
                i += 1
                continue
            if ch == "$" and nxt == "{":
                template_depth += 1
                i += 2
                continue
            if ch == "}" and template_depth > 0:
                template_depth -= 1
                i += 1
                continue
            i += 1
            continue
        if ch == '"':
            in_string_double = True
            i += 1
            continue
        if ch == "'":
            in_string_single = True
            i += 1
            continue
        if ch == "`":
            in_template = True
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


def _normalize_ts_signature(
    params_text: str,
    return_type: Optional[str],
) -> str:
    """Strip param names from ``a: T, b?: U = default`` → ``T, U``."""
    param_types = _strip_ts_param_names(params_text)
    head = "fun"
    body = f"({param_types})"
    tail = f" -> {return_type.strip()}" if return_type else ""
    return f"{head}{body}{tail}"


def _strip_ts_param_names(params_text: str) -> str:
    text = (params_text or "").strip()
    if not text:
        return ""
    parts = _split_ts_params(text)
    out: list[str] = []
    for part in parts:
        cleaned = part.strip()
        if not cleaned:
            continue
        if "{" in cleaned and "}" in cleaned:
            out.append("object")
            continue
        cleaned = cleaned.lstrip("?")
        colon_idx = _find_top_level_colon(cleaned)
        if colon_idx < 0:
            out.append(cleaned)
            continue
        type_part = cleaned[colon_idx + 1:].strip()
        type_part = type_part.split("=", 1)[0].strip()
        out.append(type_part)
    return ", ".join(out)


def _split_ts_params(text: str) -> list[str]:
    depth = 0
    last = 0
    parts: list[str] = []
    for i, ch in enumerate(text):
        if ch in "<([{":
            depth += 1
        elif ch in ">)]}":
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
        if ch in "<([{":
            depth += 1
        elif ch in ">)]}":
            if depth > 0:
                depth -= 1
        elif ch == ":" and depth == 0:
            return i
    return -1


__all__ = [
    "TypeScriptSymbol",
    "TypeScriptFileInfo",
    "parse_typescript_file",
]
