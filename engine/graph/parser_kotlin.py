"""Pragmatic regex-based Kotlin parser.

Extracts package, imports, top-level symbols, DI annotations, i18n keys, test
tags, **and reuse-intelligence metadata**: visibility, signature, extension
receiver type, body hash + tokens, modifiers.

Not an AST — best-effort, downstream consumers tolerate Optional fields.
Switch to tree-sitter for v2 if accuracy bites.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from engine.graph._body_text import (
    extract_body_tokens,
    extract_function_body,
    find_opening_brace,
    hash_body,
    tokens_to_json,
)

_RE_PACKAGE = re.compile(r"^\s*package\s+([\w\.]+)", re.MULTILINE)
_RE_IMPORT = re.compile(r"^\s*import\s+([\w\.\*]+)(?:\s+as\s+\w+)?\s*$", re.MULTILINE)

# Function-only modifiers tracked separately from the kind modifier list
# (class/object/interface modifiers are mostly orthogonal).
_FUN_MODIFIERS = (
    "inline",
    "suspend",
    "infix",
    "operator",
    "tailrec",
    "crossinline",
    "noinline",
    "external",
)

# Class/object/interface modifiers (existing list extended).
_TYPE_MODIFIERS = (
    "open",
    "abstract",
    "final",
    "sealed",
    "data",
    "inner",
    "enum",
    "annotation",
    "companion",
    "value",
)

_ALL_MODIFIERS = _FUN_MODIFIERS + _TYPE_MODIFIERS + ("inline",)


def _mask_strings_and_comments(text: str) -> str:
    """Return ``text`` with the contents of strings and comments replaced
    by spaces, preserving overall length so character offsets and line
    counts stay aligned. Used to pre-process source before running
    ``_RE_DECL.finditer`` so that ``fun``/``class``/``object`` tokens
    inside literals or comments don't produce false-positive symbols
    (R2.4).

    Handled forms:
      - Triple-quoted raw strings ``\"\"\" ... \"\"\"`` (multi-line).
      - Double-quoted strings ``" ... "`` with ``\\"`` escapes (single line).
      - Single-quoted char literals ``' ... '`` with ``\\'`` escapes.
      - Block comments ``/* ... */`` (multi-line; newlines preserved).
      - Line comments ``// ...`` to end-of-line.

    Delimiters themselves are kept in place; only the *content* is
    masked, so positions remain stable.
    """
    n = len(text)
    out = list(text)
    i = 0
    while i < n:
        ch = text[i]
        # Triple-quoted raw string.
        if ch == '"' and text.startswith('"""', i):
            end = text.find('"""', i + 3)
            if end == -1:
                # Unterminated — mask to EOF, keep newlines for line count.
                for j in range(i + 3, n):
                    if text[j] != "\n":
                        out[j] = " "
                return "".join(out)
            for j in range(i + 3, end):
                if text[j] != "\n":
                    out[j] = " "
            i = end + 3
            continue
        # Block comment.
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            end = text.find("*/", i + 2)
            if end == -1:
                for j in range(i + 2, n):
                    if text[j] != "\n":
                        out[j] = " "
                return "".join(out)
            for j in range(i + 2, end):
                if text[j] != "\n":
                    out[j] = " "
            i = end + 2
            continue
        # Line comment.
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            j = i + 2
            while j < n and text[j] != "\n":
                out[j] = " "
                j += 1
            i = j
            continue
        # Double-quoted string (single-line semantics is enough here).
        if ch == '"':
            j = i + 1
            while j < n and text[j] != "\n":
                if text[j] == "\\" and j + 1 < n:
                    out[j] = " "
                    out[j + 1] = " "
                    j += 2
                    continue
                if text[j] == '"':
                    break
                out[j] = " "
                j += 1
            i = j + 1 if j < n and text[j] == '"' else j
            continue
        # Single-quoted char literal.
        if ch == "'":
            j = i + 1
            while j < n and text[j] != "\n":
                if text[j] == "\\" and j + 1 < n:
                    out[j] = " "
                    out[j + 1] = " "
                    j += 2
                    continue
                if text[j] == "'":
                    break
                out[j] = " "
                j += 1
            i = j + 1 if j < n and text[j] == "'" else j
            continue
        i += 1
    return "".join(out)


# Top-level declarations. Multi-modifier slot via repeated non-capturing group;
# optional extension receiver before the name.
_RE_DECL = re.compile(
    r"""
    ^(?P<indent>[ \t]*)
    (?:(?P<visibility>public|private|internal|protected)\s+)?
    (?P<modifiers>(?:(?:%s)\s+)*)
    (?P<kind>class|object|interface|fun|val|var)\s+
    (?:<[^>]+>\s+)?
    (?:(?P<receiver>[A-Z][\w]*(?:<[^>]*>)?(?:\?)?)\s*\.\s*)?
    (?P<name>[A-Za-z_][A-Za-z0-9_]*)
    """
    % "|".join(sorted(set(_ALL_MODIFIERS), key=len, reverse=True)),
    re.MULTILINE | re.VERBOSE,
)

_RE_ANNOTATION = re.compile(r"@([A-Z][A-Za-z0-9_]*)(?:\(([^)]*)\))?")

_KOIN_ANNOTATIONS = {"Single", "Factory", "KoinViewModel", "Module", "ComponentScan", "Scope", "Scoped"}
_COMPOSABLE_ANNOTATION = "Composable"

# i18n usage — stringResource(R.string.X) ou helpers como i18n("a.b.c")
_RE_STRING_RESOURCE = re.compile(r"stringResource\(\s*R\.string\.([A-Za-z_][A-Za-z0-9_]*)\s*[\),]")
_RE_I18N_HELPER = re.compile(r"""i18n\(\s*["']([^"']+)["']""")

# Test tags — Modifier.testTag("literal") OR Modifier.testTag(AuthTestIds.X.Y)
_RE_TEST_TAG_LITERAL = re.compile(r"""testTag\(\s*["']([^"']+)["']\s*\)""")
_RE_TEST_TAG_REF = re.compile(r"testTag\(\s*([A-Z][A-Za-z0-9_\.]+)\s*\)")

# Firebase markers
_RE_FIREBASE = re.compile(
    r"\b(Firebase(?:Firestore|Auth|Storage|Messaging|Crashlytics|Analytics|App)?"
    r"|FirebaseAuth\b|FirebaseFirestore\b)\b"
)


@dataclass(frozen=True)
class KotlinSymbol:
    """Single Kotlin declaration extracted from a source file."""

    file_path: str
    package: str
    name: str
    kind: str
    line: int
    annotations: tuple[str, ...]
    parent_class: Optional[str]
    visibility: str = "public"
    signature: Optional[str] = None
    receiver_type: Optional[str] = None
    body_hash: Optional[str] = None
    body_tokens: Optional[str] = None
    modifiers: tuple[str, ...] = field(default_factory=tuple)
    body: Optional[str] = None


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

    # Run _RE_DECL against a mask where string/comment content has been
    # replaced by spaces (offsets preserved). This filters out false
    # positives like `fun fake() {}` written inside a raw string or
    # `/* class Foo */` — see R2.4.
    masked = _mask_strings_and_comments(text)

    for match in _RE_DECL.finditer(masked):
        kind = match.group("kind")
        name = match.group("name")
        if not name:
            continue
        line_no = text.count("\n", 0, match.start()) + 1
        ann_block = _annotations_before(lines, line_no - 1)
        annotations = tuple(_extract_annotation_names(ann_block))
        is_top_level = (match.group("indent") or "") == ""
        visibility = (match.group("visibility") or "public").strip()
        receiver = (match.group("receiver") or None)
        modifiers_str = match.group("modifiers") or ""
        modifiers = tuple(m for m in modifiers_str.split() if m)

        signature: Optional[str] = None
        body_hash: Optional[str] = None
        body_tokens_json: Optional[str] = None
        body_text: Optional[str] = None

        if kind == "fun":
            signature, body_text = _parse_function_tail(text, match.end(), receiver)
            if body_text is not None:
                body_hash = hash_body(body_text)
                tokens = extract_body_tokens(body_text, language="kotlin")
                body_tokens_json = tokens_to_json(tokens) if tokens else None

        symbols.append(
            KotlinSymbol(
                file_path=str(path),
                package=package,
                name=name,
                kind=_normalize_kind(kind, modifiers, annotations),
                line=line_no,
                annotations=annotations,
                parent_class=None if is_top_level else _enclosing_class(lines, line_no - 1),
                visibility=visibility,
                signature=signature,
                receiver_type=receiver,
                body_hash=body_hash,
                body_tokens=body_tokens_json,
                modifiers=modifiers,
                body=body_text,
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


def _parse_function_tail(
    source: str,
    decl_end_offset: int,
    receiver: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    """Walk past the function declaration to capture signature + body.

    Returns ``(canonical_signature, body_text)``. Both may be ``None`` for
    abstract functions, expression bodies (``fun foo() = ...``), or anything
    the brace scanner can't close.
    """
    n = len(source)
    i = decl_end_offset

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
        return_end = _find_return_type_end(source, return_start)
        return_type = source[return_start:return_end].strip() or None
        i = return_end

    while i < n and source[i].isspace():
        i += 1

    body_text: Optional[str] = None
    if i < n and source[i] == "{":
        body_text = extract_function_body(source, i, language="kotlin")
    elif i < n and source[i] == "=":
        body_text = None

    signature = _normalize_kotlin_signature(params_text, return_type, receiver)
    return signature, body_text


def _scan_matching_paren(source: str, open_offset: int) -> Optional[int]:
    """Return the offset of the `)` matching ``open_offset``'s `(`.

    Respects strings (single, double, triple-double) and comments. ``None`` if
    not balanced before EOF.
    """
    if source[open_offset] != "(":
        return None
    depth = 1
    i = open_offset + 1
    n = len(source)
    in_line_comment = False
    in_block_comment = False
    in_string_double = False
    in_string_triple = False
    in_string_single = False

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
        if in_string_triple:
            if ch == '"' and source[i:i + 3] == '"""':
                in_string_triple = False
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
        if ch == '"' and source[i:i + 3] == '"""':
            in_string_triple = True
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

        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return None


def _find_return_type_end(source: str, start: int) -> int:
    """Return type ends at the first `{`, `=`, newline-then-non-space, or `where`.

    Captures simple return types including generics like ``List<T?>?``.
    """
    n = len(source)
    i = start
    depth_angle = 0
    while i < n:
        ch = source[i]
        if ch == "<":
            depth_angle += 1
        elif ch == ">":
            if depth_angle > 0:
                depth_angle -= 1
        elif depth_angle == 0:
            if ch in "{=\n":
                return i
            if ch == "w" and source[i:i + 5] == "where":
                return i
        i += 1
    return n


def _normalize_kotlin_signature(
    params_text: str,
    return_type: Optional[str],
    receiver: Optional[str],
) -> str:
    """Strip parameter names + collapse generics → stable canonical form.

    Examples::

        ("throwable: Throwable, code: ErrorCode", "Boolean", None)
        → "fun(Throwable, ErrorCode): Boolean"
        ("value: T", "T?", "MutableList<T : Any>")
        → "MutableList<T>.fun(T): T?"
    """
    param_types = _strip_param_names(params_text)
    rt = _simplify_generics(return_type) if return_type else None
    head = f"{_simplify_generics(receiver)}.fun" if receiver else "fun"
    body = f"({param_types})"
    tail = f": {rt}" if rt else ""
    return f"{head}{body}{tail}"


def _strip_param_names(params_text: str) -> str:
    """Drop ``name:`` prefixes, leave types + commas + generics intact."""
    text = (params_text or "").strip()
    if not text:
        return ""

    parts = _split_top_level_commas(text)
    out: list[str] = []
    for part in parts:
        cleaned = part.strip()
        if not cleaned:
            continue
        cleaned = re.sub(r"^(?:vararg|crossinline|noinline)\s+", "", cleaned)
        colon_idx = _find_top_level_colon(cleaned)
        type_part = cleaned[colon_idx + 1:].strip() if colon_idx >= 0 else cleaned
        type_part = type_part.split("=", 1)[0].strip()
        out.append(_simplify_generics(type_part) or type_part)
    return ", ".join(out)


def _split_top_level_commas(text: str) -> list[str]:
    """Split by commas not inside generics/parens."""
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


def _simplify_generics(text: Optional[str]) -> str:
    """Collapse generic bounds: ``<T : Any, U : Comparable<U>>`` → ``<T, U>``."""
    if not text:
        return ""
    text = text.strip()
    out: list[str] = []
    depth = 0
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "<":
            depth += 1
            out.append(ch)
            i += 1
            block_start = i
            inner_depth = 1
            # R3.7 hardening: guarantee progress on every iteration even
            # under pathological inputs (the existing `i += 1` already
            # ran on both branches, but it sat AFTER the conditional —
            # if a future edit ever short-circuits with `continue`
            # without incrementing, we'd hang on malformed input like
            # `List<T` or `<<<`). Hoist the increment to the end and
            # add an explicit hard ceiling tied to remaining text
            # length: under no condition can the inner loop run more
            # iterations than there are characters left.
            start_i = i
            max_iter = len(text) - start_i + 1
            iter_count = 0
            while i < len(text) and inner_depth > 0 and iter_count < max_iter:
                if text[i] == "<":
                    inner_depth += 1
                elif text[i] == ">":
                    inner_depth -= 1
                    if inner_depth == 0:
                        break
                i += 1
                iter_count += 1
            inner = text[block_start:i]
            stripped_params = ", ".join(
                _strip_bound(p) for p in _split_top_level_commas(inner)
            )
            out.append(_simplify_generics_inner(stripped_params))
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _simplify_generics_inner(text: str) -> str:
    """Recursively simplify a comma-separated generic param list."""
    return ", ".join(_simplify_generics(p.strip()) for p in _split_top_level_commas(text))


def _strip_bound(param: str) -> str:
    """``T : Any`` → ``T``; ``out T`` → ``out T``; ``reified T`` → ``T``."""
    cleaned = param.strip()
    if ":" in cleaned:
        cleaned = cleaned.split(":", 1)[0].strip()
    cleaned = re.sub(r"^(?:in|out|reified)\s+", "", cleaned)
    return cleaned


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


def _normalize_kind(
    kind: str,
    modifiers: tuple[str, ...],
    annotations: tuple[str, ...],
) -> str:
    mods = set(modifiers)
    if kind == "class":
        if "sealed" in mods:
            return "sealed_class"
        if "enum" in mods:
            return "enum"
        if "data" in mods:
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


# Re-export for tests / external callers that previously imported from here.
__all__ = [
    "KotlinSymbol",
    "KotlinFileInfo",
    "parse_kotlin_file",
]
