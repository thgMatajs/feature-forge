"""Brace-aware function body extraction + normalization for reuse-intelligence.

Used by parser_kotlin, parser_swift and parser_typescript to:
- extract the textual body between `{ ... }` of a function declaration
- normalize the text (strip comments, collapse whitespace) for stable hashing
- tokenize for cross-language Jaccard similarity

Hand-rolled scanner because we want zero new dependencies. Robust enough for
99% of real-world cases — falls back to None when the brace counter can't
close, so callers must treat body_hash as Optional.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Optional

# Languages that go through this helper. Used only to pick comment / string
# rules; everything else is shared.
_SUPPORTED_LANGS = frozenset(
    {"kotlin", "swift", "typescript", "javascript", "java", "objc"}
)


def extract_function_body(
    source: str,
    open_brace_offset: int,
    language: str = "kotlin",
) -> Optional[str]:
    """Return text between the opening `{` at ``open_brace_offset`` and its match.

    ``open_brace_offset`` is the character index of the opening brace in
    ``source`` (callers usually compute it from a regex match end + a `{` search).

    Strings, character literals (Swift/Kotlin char), template strings (TS) and
    line/block comments are all respected — `{` / `}` inside them do not count.

    Returns ``None`` if the body can't be closed (truncated file, mismatched
    braces, regex hit a fake declaration site).
    """
    if language not in _SUPPORTED_LANGS:
        return None
    if open_brace_offset < 0 or open_brace_offset >= len(source):
        return None
    if source[open_brace_offset] != "{":
        return None

    depth = 1
    i = open_brace_offset + 1
    start = i
    n = len(source)

    # State flags for in-string / in-comment scanning.
    in_line_comment = False
    in_block_comment = False
    in_string_double = False
    in_string_triple = False    # Kotlin """..."""
    in_string_single = False    # Swift/Kotlin char literal, JS single-quote
    in_template = False         # TS / JS backtick template
    template_depth = 0          # ${...} inside `...`

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
            if ch == "\\" and nxt:
                i += 2
                continue
            if ch == '"':
                in_string_double = False
            i += 1
            continue
        if in_string_single:
            if ch == "\\" and nxt:
                i += 2
                continue
            if ch == "'":
                in_string_single = False
            i += 1
            continue
        if in_template:
            if ch == "\\" and nxt:
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

        # Not inside a string/comment — check entry conditions.
        if ch == "/" and nxt == "/":
            in_line_comment = True
            i += 2
            continue
        if ch == "/" and nxt == "*":
            in_block_comment = True
            i += 2
            continue
        if language in {"kotlin", "swift"} and ch == '"' and source[i:i + 3] == '"""':
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
        if language in {"typescript", "javascript"} and ch == "`":
            in_template = True
            i += 1
            continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return source[start:i]
        i += 1

    return None


_RE_LINE_COMMENT = re.compile(r"//[^\n]*")
_RE_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_RE_WS = re.compile(r"\s+")


def normalize_body(text: str) -> str:
    """Strip comments + collapse whitespace.

    Preserves identifiers, operators, literals — anything that affects
    semantics. The result is deterministic across whitespace-only refactors
    and comment edits.
    """
    cleaned = _RE_BLOCK_COMMENT.sub(" ", text)
    cleaned = _RE_LINE_COMMENT.sub("", cleaned)
    cleaned = _RE_WS.sub(" ", cleaned).strip()
    return cleaned


def hash_body(text: str) -> str:
    """SHA-1 of the normalized body, truncated to 16 hex chars (64 bits).

    Collision domain: 64 bits → birthday collision probability ~50%
    around 2^32 (~4 bilhões) de bodies distintos. Na escala de v1.1
    (graph guarda ≤ alguns milhões de símbolos mesmo em monorepos),
    a probabilidade de colisão é desprezível. Se surgirem projetos com
    >100M símbolos, subir pra SHA-1 completo (40 hex) ou BLAKE3-128.

    Truncamento escolhido porque cada símbolo grava 1 hash em SQLite —
    subir pra BLAKE3-128 (32 chars) inflaria a coluna de hash ~2x; SHA-1
    completo (40 chars) ~2.5x. Ganho de safety em colisão irrelevante na
    escala de v1.1.
    """
    return hashlib.sha1(normalize_body(text).encode("utf-8")).hexdigest()[:16]


_RE_TOKEN = re.compile(
    r"""
    [A-Za-z_][A-Za-z0-9_]*       # identifier
    | \d+(?:\.\d+)?              # numeric literal
    | "([^"\\]|\\.)*"            # double-quoted string content
    | '([^'\\]|\\.)*'            # single-quoted string content
    """,
    re.VERBOSE,
)


# Tokens that show up in every body and add no signal for cross-language
# similarity — pruning them sharpens Jaccard scores.
_NOISE_TOKENS_PER_LANG: dict[str, frozenset[str]] = {
    "kotlin": frozenset(
        {
            "val", "var", "fun", "this", "return", "if", "else", "when",
            "null", "true", "false", "is", "as", "in", "out", "by",
        }
    ),
    "swift": frozenset(
        {
            "let", "var", "func", "self", "return", "if", "else", "switch",
            "nil", "true", "false", "guard", "case", "where",
        }
    ),
    "typescript": frozenset(
        {
            "let", "var", "const", "function", "this", "return", "if", "else",
            "switch", "null", "undefined", "true", "false", "of", "in", "as",
        }
    ),
    "javascript": frozenset(
        {
            "let", "var", "const", "function", "this", "return", "if", "else",
            "switch", "null", "undefined", "true", "false", "of", "in",
        }
    ),
    "java": frozenset(
        {
            "public", "private", "protected", "class", "interface", "enum",
            "return", "if", "else", "for", "while", "do", "switch", "case",
            "break", "continue", "new", "this", "super", "null", "true",
            "false", "void", "int", "long", "double", "float", "boolean",
            "char", "byte", "short", "final", "static", "abstract", "extends",
            "implements", "import", "package", "try", "catch", "finally",
            "throw", "throws", "synchronized", "volatile", "transient",
            "instanceof", "assert", "record", "sealed", "non-sealed", "var",
        }
    ),
    "objc": frozenset(
        {
            "self", "super", "return", "if", "else", "for", "while", "do",
            "switch", "case", "break", "continue", "nil", "null", "yes", "no",
            "true", "false", "id", "instancetype", "void", "int", "bool",
            "nsinteger", "nsuinteger", "cgfloat", "nsstring", "nsarray",
            "nsdictionary", "nsset", "nsobject", "strong", "weak", "copy",
            "assign", "retain", "nonatomic", "atomic", "readwrite", "readonly",
            "in", "out", "inout", "byref", "bycopy", "oneway", "typedef",
            "struct", "union", "enum", "const", "static", "extern",
            "@public", "@protected", "@private", "@package", "@class",
            "@selector", "@protocol", "@required", "@optional", "@end",
            "@synthesize", "@dynamic", "@synchronized", "@try", "@catch",
            "@finally", "@throw", "@autoreleasepool", "@encode",
            "@compatibility_alias", "@defs", "@property", "@implementation",
            "@interface",
        }
    ),
}


def extract_body_tokens(text: str, language: str = "kotlin") -> frozenset[str]:
    """Tokenize normalized body into identifiers + numeric literals + string content.

    Lowercased. Language-specific noise tokens filtered (`val`, `fun`, `let`,
    etc.). Returned as a frozenset for stable comparison.

    Empty input or unsupported language → empty frozenset.
    """
    if not text or language not in _NOISE_TOKENS_PER_LANG:
        return frozenset()
    cleaned = normalize_body(text)
    noise = _NOISE_TOKENS_PER_LANG[language]
    tokens: set[str] = set()
    for match in _RE_TOKEN.finditer(cleaned):
        raw = match.group(0)
        if raw.startswith('"') or raw.startswith("'"):
            tok = raw[1:-1].lower()
        else:
            tok = raw.lower()
        if not tok or tok in noise:
            continue
        tokens.add(tok)
    return frozenset(tokens)


def tokens_to_json(tokens: frozenset[str]) -> str:
    """Serialize token set to JSON array (sorted for determinism)."""
    return json.dumps(sorted(tokens), separators=(",", ":"))


def tokens_from_json(payload: Optional[str]) -> frozenset[str]:
    """Deserialize JSON array → frozenset. Tolerant to NULL / malformed input."""
    if not payload:
        return frozenset()
    try:
        data = json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        return frozenset()
    if not isinstance(data, list):
        return frozenset()
    return frozenset(str(t) for t in data if isinstance(t, str))


def jaccard_similarity(a: frozenset[str], b: frozenset[str]) -> float:
    """Standard Jaccard: ``|A ∩ B| / |A ∪ B|``. Returns 0.0 for empty union."""
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def find_opening_brace(source: str, start: int) -> Optional[int]:
    """Locate the first `{` at or after ``start`` skipping whitespace.

    Returns ``None`` if a non-whitespace, non-`{` character is hit first
    (signature continuations, abstract function, expression-body `fun foo() = ...`).
    """
    n = len(source)
    i = start
    while i < n:
        ch = source[i]
        if ch.isspace():
            i += 1
            continue
        if ch == "{":
            return i
        return None
    return None
