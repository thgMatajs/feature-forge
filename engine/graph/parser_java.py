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
    _SUPPORTED_LANGS,
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

# H-010 coupling guard: ``_BODY_LANG`` precisa estar registrado em
# ``_SUPPORTED_LANGS`` — senão ``extract_function_body`` retorna None
# silenciosamente e parser_java perde body extraction. Assertion garante
# detect-at-import: se alguém remover "java" do set, ImportError quebra
# cedo em vez de pasinho silencioso em produção.
assert "java" in _SUPPORTED_LANGS, (
    "_BODY_LANG='java' must be registered in engine.graph._body_text._SUPPORTED_LANGS"
)

_RE_PACKAGE = re.compile(r"^\s*package\s+([\w\.]+)\s*;", re.MULTILINE)
_RE_IMPORT = re.compile(r"^\s*import\s+(?:static\s+)?([\w\.\*]+)\s*;", re.MULTILINE)

# Class/interface/enum/record/annotation declarations.
#
# P-N-010 / gemini parser_java:65 (REVIEW PR #16): generics com bounds
# (``<T extends Serializable>``) e nested 1-level (``<T extends Comparable<T>>``)
# precisam casar. Antes: ``<\w+(?:,\s*\w+)*>`` aceitava só identifiers
# bare separados por vírgula — bounds quebravam.
#
# Padrão aceita 1 nível de aninhamento balanced:
#   <[^<>]*(?:<[^<>]*>[^<>]*)*>
# Aceita ``<T>``, ``<T, U>``, ``<T extends Comparable<T>>``,
# ``<K, V extends Number>``. Não cobre 3+ níveis (raros em prática), e
# tree-sitter v1.4 endereça regex fragility geral (spec §Risks R1).
_RE_CLASS = re.compile(
    r"(?:(?:public|private|protected|abstract|final|static|sealed|non-sealed)\s+)*"
    r"(?:class|interface|@interface|enum|record)\s+"
    r"(\w+)"
    r"(?:\s*<[^<>]*(?:<[^<>]*>[^<>]*)*>)?"
    r"(?:\s+extends\s+[\w\.]+(?:<[^<>]*(?:<[^<>]*>[^<>]*)*>)?)?"
    r"(?:\s+implements\s+[\w\.,\s<>]+)?"
    r"\s*\{",
    re.MULTILINE,
)

# Reserved words that look like a "type" token when the regex matches
# a call-expression statement (e.g. ``return foo(x);`` or ``new Foo(z);``).
# C-001 (REVIEW v1.3.0): without this filter, the regex captures phantom
# symbols from every call/new/throw/control-flow statement, inflating
# symbols table 5-10x on real Android repos and corrupting Q12/Q13
# body-hash dup detection. Reserved words can never be the *type* of a
# method declaration in valid Java, so filtering them out is safe.
_JAVA_RESERVED_TYPE_BLOCKLIST = frozenset({
    "return", "new", "this", "super", "throw", "if", "while", "for",
    "switch", "do", "else", "case", "break", "continue", "yield",
    "synchronized", "try", "catch", "finally", "assert", "instanceof",
})

# P-N-010 / gemini parser_java:89 (REVIEW PR #16): nested generics no
# return type (``List<Map<String, Object>>``) precisam casar. Antes:
# ``(<[^>]*>)?`` parava no primeiro ``>`` — só profundidade 1 lisa.
# Padrão agora aceita 1 nível de aninhamento:
# ``<[^<>]*(?:<[^<>]*>[^<>]*)*>``. Reaproveitado pra ambos os slots de
# generics (return-type qualifier + return-type capture).
_RE_METHOD = re.compile(
    r"(?:(?:public|private|protected|static|final|abstract|synchronized|native|default)\s+)*"
    r"(?:\w+(?:\[\])?(?:<[^<>]*(?:<[^<>]*>[^<>]*)*>)?\.)?"
    r"(\w+(?:<[^<>]*(?:<[^<>]*>[^<>]*)*>)?(?:\[\])?)"
    r"\s+"
    r"(\w+)\s*"
    r"\(([^)]*)\)"
    # Optional ``throws Exception1, Exception2`` clause between ``)`` and
    # ``{``/``;`` (T-N-008 / REVIEW PR #16).
    r"(?:\s*throws\s+[\w\.,\s]+)?"
    r"\s*(?:\{|\s*;)",
    re.MULTILINE,
)

# Visibility prefix detection
_VISIBILITY_RE = re.compile(r"(public|private|protected)")

# Comment strippers — single-line (``// ...``) and block (``/* ... */``).
# Usados antes de _VISIBILITY_RE pra evitar false positive em comentários
# como ``// public method``. M-009 (REVIEW v1.3.0).
_RE_LINE_COMMENT = re.compile(r"//[^\n]*")
_RE_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def _strip_comments(text: str) -> str:
    """Remove block and line comments — defensive against visibility false-positives."""
    text = _RE_BLOCK_COMMENT.sub("", text)
    text = _RE_LINE_COMMENT.sub("", text)
    return text


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
    """Parse a single .java file. Returns a populated ``JavaFileInfo``.

    H-001 (REVIEW v1.3.0): ``errors="replace"`` alinha com parser_kotlin /
    parser_swift — bytes inválidos viram ``U+FFFD`` em vez de explodir o
    builder em UnicodeDecodeError. Best-effort parsing tolera lixo.
    """
    source = path.read_text(encoding="utf-8", errors="replace")
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
        # M-009: stripa comments antes da detecção pra evitar false positive
        # quando ``// public method`` aparece antes da declaração.
        vis_m = _VISIBILITY_RE.search(_strip_comments(kind_raw))
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

        # C-001 (REVIEW v1.3.0): rejeita matches onde o "tipo" é uma reserved
        # word — só pode acontecer quando o regex casou uma call-expression
        # statement (``return foo(x);``), ``new Foo(z);``, ``throw e(x);`` etc.
        # Em declaração de método válida, o token de tipo NUNCA é palavra
        # reservada. Sem este filtro, instâncias de classes viram "constructor"
        # fantasma (via heurística is_constructor mais abaixo), inflando o
        # symbols table e corrompendo Q12/Q13 (body-hash dup detection).
        # Strip ``<...>`` generic suffix antes do lookup pra que ``return<T>``
        # (sintaticamente impossível em Java, mas defensivo) também caia.
        raw_type_base = raw_type.split("<", 1)[0]
        if raw_type_base in _JAVA_RESERVED_TYPE_BLOCKLIST:
            continue

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
        # M-009: stripa comments do full_match e da janela de preceding
        # antes da detecção pra evitar matchear ``// public xyz`` em vez do
        # modifier real da declaração.
        vis_m = _VISIBILITY_RE.search(_strip_comments(full_match))
        if vis_m:
            visibility = vis_m.group(1)
        else:
            vis_m = _VISIBILITY_RE.search(_strip_comments(preceding[-100:]))
            if vis_m:
                visibility = vis_m.group(1)

        modifiers = []
        # P-N-008 / gemini parser_java:273 (REVIEW PR #16): split em
        # ``full_match`` inteiro inclui params como ``(final int x)``;
        # ``final`` como param qualifier seria capturado como modifier do
        # método. Limitar busca ao prefixo ANTES do nome do método.
        idx = full_match.find(method_name)
        modifier_window = full_match[:idx] if idx > 0 else full_match
        for token in modifier_window.split():
            if token in {"static", "final", "abstract", "synchronized", "native", "default"}:
                if token not in modifiers:
                    modifiers.append(token)

        signature = f"{raw_type} {method_name}({params})"

        # Body extraction — locate the opening brace inside ``full_match``
        # and resolve to an absolute offset in ``source``. If the match
        # ended with `;` (no body), leave body fields ``None``.
        # C-001 (REVIEW PR #16): sem type-hints aqui — mypy reportava
        # ``no-redef`` porque ``body``/``body_hash``/``body_tokens`` já
        # foram declarados com type hint no loop anterior (linhas 187-191).
        # Reatribuição simples preserva o tipo inferido + zera entre iters.
        body = None
        body_hash = None
        body_tokens = None
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
