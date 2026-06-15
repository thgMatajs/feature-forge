"""Pragmatic regex-based Java parser.

Extracts package, imports, top-level symbols with visibility, signature,
and body text. Mirrors the Kotlin parser pattern (KotlinFileInfo → JavaFileInfo).

Not an AST — best-effort, downstream consumers tolerate Optional fields.
Switch to tree-sitter for v2 if accuracy bites.

Body extraction reuses ``engine.graph._body_text`` with ``language="java"``.
Java syntax is C-style and shares the same comment/string lexical rules
covered by the shared scanner (``//``, ``/* */``, double-quoted strings,
single-quoted char literals). Java has no triple-quoted strings or
backtick templates — the language-specific branches in
``extract_function_body`` only activate for kotlin/swift (triple-quote
raw strings) and typescript/javascript (backtick templates), so the Java
path is exactly the C-style baseline. Onda 6 moved ``java`` into
``_SUPPORTED_LANGS`` + ``_NOISE_TOKENS_PER_LANG``, so this parser passes
the canonical language label end-to-end.
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

# Language passed to shared body helpers. Onda 6 registrou ``java`` em
# ``_SUPPORTED_LANGS`` + ``_NOISE_TOKENS_PER_LANG`` (engine/graph/_body_text.py),
# então o scanner agora trata Java como C-style baseline (sem triple-quote
# Kotlin nem backtick TS) corretamente.
_BODY_LANG = "java"

_RE_PACKAGE = re.compile(r"^\s*package\s+([\w\.]+)\s*;", re.MULTILINE)
_RE_IMPORT = re.compile(r"^\s*import\s+(?:static\s+)?([\w\.\*]+)\s*;", re.MULTILINE)

# Class/interface/enum/record/annotation declarations.
_RE_CLASS = re.compile(
    r"(?:(?:public|private|protected|abstract|final|static|sealed|non-sealed)\s+)*"
    r"(?:class|interface|@interface|enum|record)\s+"
    r"(\w+)"
    r"(?:\s*<\w+(?:,\s*\w+)*>)?"
    r"(?:\s+extends\s+\w+(?:\.\w+)*(?:<[^>]*>)?)?"
    r"(?:\s+implements\s+[\w\.,\s<>]+)?"
    r"\s*\{",
    re.MULTILINE,
)

_RE_METHOD = re.compile(
    r"(?:(?:public|private|protected|static|final|abstract|synchronized|native|default)\s+)*"
    r"(?:\w+(?:\[\])?(?:<[^>]*>)?\.)?"
    r"(\w+(?:<[^>]*>)?)"
    r"\s+"
    r"(\w+)\s*"
    r"\(([^)]*)\)"
    r"\s*(?:\{|\s*;)",
    re.MULTILINE,
)

# Visibility prefix detection
_VISIBILITY_RE = re.compile(r"(public|private|protected)")


@dataclass
class JavaSymbolInfo:
    name: str
    kind: str  # "class" | "interface" | "enum" | "record" | "annotation" | "method" | "constructor"
    visibility: str = "internal"  # alinhado com Kotlin internal (package-scoped)
    signature: Optional[str] = None
    line: int = 0
    body: Optional[str] = None
    body_hash: Optional[str] = None
    body_tokens: Optional[str] = None
    modifiers: list[str] = field(default_factory=list)
    receiver_type: Optional[str] = None


@dataclass
class JavaFileInfo:
    package: Optional[str]
    imports: list[str]
    symbols: list[JavaSymbolInfo]


def parse_java_file(path: Path) -> JavaFileInfo:
    """Parse a single .java file. Returns a populated ``JavaFileInfo``."""
    source = path.read_text(encoding="utf-8")
    return _parse_java(source)


def _parse_java(source: str) -> JavaFileInfo:
    package: Optional[str] = None
    pkg_m = _RE_PACKAGE.search(source)
    if pkg_m:
        package = pkg_m.group(1)

    imports: list[str] = _RE_IMPORT.findall(source)

    symbols: list[JavaSymbolInfo] = []

    # Top-level type declarations.
    for m in _RE_CLASS.finditer(source):
        kind_raw = m.group(0)
        name = m.group(1)
        start = m.start()

        # Infer kind from keyword. ``@interface`` must be checked before
        # plain ``interface`` to avoid mis-classifying annotations.
        if "@interface" in kind_raw:
            kind = "annotation"
        elif re.search(r"\binterface\b", kind_raw):
            kind = "interface"
        elif re.search(r"\benum\b", kind_raw):
            kind = "enum"
        elif re.search(r"\brecord\b", kind_raw):
            kind = "record"
        else:
            kind = "class"

        line = source[:start].count("\n") + 1

        visibility = "internal"  # alinhado com Kotlin internal (package-scoped)
        vis_m = _VISIBILITY_RE.search(kind_raw)
        if vis_m:
            visibility = vis_m.group(1)

        # Collect modifiers between the start of the match and the type name.
        mods_raw = kind_raw[: kind_raw.index(name)] if name in kind_raw else ""
        modifiers = [
            t for t in mods_raw.split()
            if t in {"abstract", "static", "final", "sealed", "non-sealed"}
        ]

        # Body extraction — the regex ends at the opening brace.
        brace_offset = find_opening_brace(source, m.end() - 1)
        body: Optional[str] = None
        if brace_offset is not None:
            body = extract_function_body(source, brace_offset, language=_BODY_LANG)
        body_hash = hash_body(body) if body is not None else None
        body_tokens = None
        if body is not None:
            tokens = extract_body_tokens(body, language=_BODY_LANG)
            body_tokens = tokens_to_json(tokens) if tokens else None

        sig_text = kind_raw.strip()
        signature = sig_text[:80] if len(sig_text) > 80 else sig_text

        symbols.append(JavaSymbolInfo(
            name=name,
            kind=kind,
            visibility=visibility,
            signature=signature,
            line=line,
            body=body,
            body_hash=body_hash,
            body_tokens=body_tokens,
            modifiers=modifiers,
        ))

    # Methods + constructors. Constructor detection compares the method
    # name to the collected class/interface/enum/record/annotation names.
    class_names = {
        s.name for s in symbols
        if s.kind in {"class", "interface", "enum", "record", "annotation"}
    }

    for m in _RE_METHOD.finditer(source):
        raw_type = m.group(1)
        method_name = m.group(2)
        params = m.group(3)
        full_match = m.group(0)

        # Constructor heuristic: method name matches an enclosing class
        # name collected above.
        is_constructor = method_name in class_names

        # Abstract / interface methods end with `;` rather than `{`.
        # Treat them as ``method`` kind (still callable surface), not
        # ``constructor`` — constructor must come from name match.
        ends_with_semicolon = full_match.rstrip().endswith(";")
        if is_constructor:
            kind = "constructor"
        else:
            kind = "method"

        line = source[:m.start()].count("\n") + 1

        # Visibility from the modifier window immediately preceding the
        # match start.
        preceding = source[max(0, m.start() - 200):m.start()]
        visibility = "internal"  # alinhado com Kotlin internal (package-scoped)
        # Also accept visibility tokens captured inside ``full_match`` (the
        # regex consumes leading modifiers via a non-capturing group).
        vis_m = _VISIBILITY_RE.search(full_match)
        if vis_m:
            visibility = vis_m.group(1)
        else:
            vis_m = _VISIBILITY_RE.search(preceding[-100:])
            if vis_m:
                visibility = vis_m.group(1)

        modifiers = []
        # Look for non-visibility modifiers inside ``full_match`` first
        # (regex's non-capturing modifier group covers them).
        for token in full_match.split():
            if token in {"static", "final", "abstract", "synchronized", "native", "default"}:
                if token not in modifiers:
                    modifiers.append(token)

        signature = f"{raw_type} {method_name}({params})"

        # Body extraction — locate the opening brace inside ``full_match``
        # and resolve to an absolute offset in ``source``. If the match
        # ended with `;` (no body), leave body fields ``None``.
        body: Optional[str] = None
        body_hash: Optional[str] = None
        body_tokens: Optional[str] = None
        if not ends_with_semicolon:
            brace_start_in_match = full_match.rfind("{")
            if brace_start_in_match >= 0:
                brace_offset = m.start() + brace_start_in_match
                body = extract_function_body(source, brace_offset, language=_BODY_LANG)
                if body is not None:
                    body_hash = hash_body(body)
                    tokens = extract_body_tokens(body, language=_BODY_LANG)
                    body_tokens = tokens_to_json(tokens) if tokens else None

        symbols.append(JavaSymbolInfo(
            name=method_name,
            kind=kind,
            visibility=visibility,
            signature=signature,
            line=line,
            body=body,
            body_hash=body_hash,
            body_tokens=body_tokens,
            modifiers=modifiers,
        ))

    return JavaFileInfo(package=package, imports=imports, symbols=symbols)


__all__ = [
    "JavaSymbolInfo",
    "JavaFileInfo",
    "parse_java_file",
]
