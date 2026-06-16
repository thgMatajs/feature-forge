"""Simplified Objective-C parser — imports + symbols only.

NO call graph (``[obj selector]`` parsing). NO full AST. Regex-based,
best-effort. Covers the most common patterns found in iOS legacy code.

This is sufficient for graph queries (Q4 symbols, Q11/12/13 dup detection
via body_hash) without the complexity of a full ObjC AST walker.
"""

from __future__ import annotations

import bisect
import logging
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

# P-N-018 / codereviewbot parser_objc:158 (REVIEW PR #16): warnings de
# ``@end`` faltando são logged em DEBUG (não printam em runtime default).
# Permite forensics em CI mas não polui stderr em uso normal.
_log = logging.getLogger(__name__)

# H-010 coupling guard: ``"objc"`` precisa estar registrado em
# ``_SUPPORTED_LANGS`` — senão ``extract_function_body(..., language="objc")``
# retorna None silenciosamente e parser_objc perde body extraction. Assertion
# detect-at-import previne pasinho silencioso em produção.
assert "objc" in _SUPPORTED_LANGS, (
    "language='objc' must be registered in engine.graph._body_text._SUPPORTED_LANGS"
)

_RE_IMPORT = re.compile(r'^#import\s+[<"]([^>"]+)[>"]', re.MULTILINE)
_RE_MODULE_IMPORT = re.compile(r'^@import\s+(\w+)\s*;', re.MULTILINE)

# P-N-003 (REVIEW PR #16): ObjC categories ``@interface Foo (CategoryName)``
# e class extensions ``@interface Foo ()`` precisam de regex próprio porque
# o paren-form não tem superclass colon. ``_RE_CATEGORY`` casa AMBOS — com
# nome de category (group 2 populado) ou anonymous (group 2 vazio = class
# extension). O builder mapeia ``kind="category"`` pra visibility=public
# (cf. builder.py:790).
#
# Distinção operacional pro consumer:
#   group(2) não-vazio → category nomeada (``UIView+Animations``)
#   group(2) vazio     → class extension (``@interface Foo ()`` —
#                        adiciona ivars/methods privados ao .m)
#
# ``_RE_INTERFACE`` mantém ordem-sensível: o match de category roda ANTES
# pra que ``@interface Foo (Bar)`` não case primeiro como class sem super.
_RE_CATEGORY = re.compile(
    r'@interface\s+(\w+)\s*\(\s*(\w*)\s*\)',
    re.MULTILINE,
)
_RE_INTERFACE = re.compile(
    r'@interface\s+(\w+)\s*(?::\s*(\w+(?:\s*<\w+>)?))?',
    re.MULTILINE,
)
_RE_PROTOCOL = re.compile(r'@protocol\s+(\w+)', re.MULTILINE)
_RE_IMPLEMENTATION = re.compile(r'@implementation\s+(\w+)', re.MULTILINE)

# Method header start — ``-`` (instance) or ``+`` (class). L-003 (REVIEW
# v1.3.0): ancora ``^[+-]\s*\(`` exige parêntese imediato após whitespace,
# impedindo que comentários ``// - here's a note`` casem. Captura toda a
# header até o primeiro ``{`` ou ``;`` pra que o parser extraia selector
# segments num passo separado (C-002).
#
# P-N-001 (REVIEW PR #16): usa lookahead ``(?=\{|;)`` em vez de consumir o
# delimitador, pra que ``m.end()`` aponte PARA o ``{`` (não depois dele).
# Sem isso, ``find_opening_brace(source, m.end())`` pulava o `{` real e
# procurava o próximo — body extraction de todo método ObjC retornava None.
#
# P-N-011 (REVIEW PR #16): rest group passa a aceitar ``\n`` (multi-line
# headers são padrão em ObjC com 3+ selectors). A âncora ``^[+-]`` no MODE
# MULTILINE garante que só linhas começando com ``+``/``-`` iniciem o match,
# então permitir ``\n`` no rest não causa over-match — o terminador ``{``
# ou ``;`` continua delimitando precisamente.
_RE_METHOD_HEADER = re.compile(
    r'^([+-])\s*'                            # 1: class/instance
    r'\(([\w\s\*<>,\[\]{}]+)\)\s*'            # 2: return type
    r'([^{;]+?)'                              # 3: rest of header (selector + params, NL ok)
    r'\s*(?=\{|;)',                           # lookahead pro body opener / no-body decl
    re.MULTILINE,
)

# Selector segment matcher — captura apenas ``label:`` (P-N-015 / gemini
# parser_objc:61 / REVIEW PR #16).
#
# Antes: ``(\w+)\s*:\s*\([^)]+\)\s*\w+`` — exigia ``(type)param`` completo,
# falhava com tipos parametrizados (``NSDictionary<NSString*, NSArray*>``),
# block types (``void (^)(void)``), const-qualified, etc. ObjC selectors
# usam só os labels antes do ``:`` — type/param annotations são opcionais
# pra reconstrução do selector canonical.
#
# Padrão simplificado: identifier + ``:`` (lookahead pra que números/dois-pontos
# em strings não casem). Para evitar casar ``ratio:1.0`` em literais ou
# tipos com generics aninhados ("``NSArray<Foo:Bar>``" — não é válido ObjC
# mas defensivo), exige whitespace, ``)`` ou início-de-rest antes do label.
_RE_SEL_SEGMENT = re.compile(
    r'(?:^|[\s)])(\w+)\s*:',
)

# Property: também aceita generics como ``NSArray<UserModel *> *users``.
# L-002 (REVIEW v1.3.0). O separador entre tipo e nome aceita ``*`` (zero
# ou mais), espaços, ou nenhum espaço quando ``*`` está colado no tipo
# (``NSArray<UserModel *>*users``).
#
# P-N-016 / gemini parser_objc:74 (REVIEW PR #16): type group expandido pra
# aceitar multi-token types e qualifiers:
# - ``unsigned int``, ``long long`` (built-in compostos)
# - ``const NSString``, ``__weak Foo`` (qualifiers)
# - ``struct CGRect``, ``union Bar`` (C interop)
# - generics aninhados (``NSArray<NSDictionary<NSString *, id> *>``)
#
# A captura group(1) acumula tokens via ``\w+(?:\s+\w+)*`` — fica greedy o
# suficiente pra ``unsigned int`` colar, mas o separador final exigido
# (``\s*\*+\s*`` ou ``\s+``) garante que o último token é tipo, e o group(2)
# captura o nome.
_RE_PROPERTY = re.compile(
    r'@property\s*(?:\([^)]*\))?\s*'
    r'(\w+(?:\s+\w+)*(?:\s*<[^>]+>)?)'   # 1: type (multi-token + generics)
    r'(?:\s*\*+\s*|\s+)'                 # ponteiros OU whitespace
    r'(\w+)\s*;',                        # 2: name
    re.MULTILINE,
)


@dataclass
class ObjcSymbolInfo:
    name: str
    kind: str  # "class" | "protocol" | "implementation" | "method" | "property" | "category" | "class_extension"
    is_class_method: bool = False  # True for + methods
    signature: Optional[str] = None
    line: int = 0
    body: Optional[str] = None
    body_hash: Optional[str] = None
    body_tokens: Optional[str] = None
    modifiers: list[str] = field(default_factory=list)
    receiver_type: Optional[str] = None


@dataclass
class ObjcFileInfo:
    imports: list[str]  # #import and @import targets
    symbols: list[ObjcSymbolInfo]


def parse_objc_file(path: Path) -> ObjcFileInfo:
    # H-001 (REVIEW v1.3.0): ``errors="replace"`` alinha com
    # parser_kotlin / parser_swift.
    source = path.read_text(encoding="utf-8", errors="replace")
    return _parse_objc(source)


def _find_end_after(end_positions: list[int], offset: int) -> Optional[int]:
    """P-N-018 (REVIEW PR #16): retorna o offset do primeiro ``@end`` a partir
    de ``offset`` via binary search em positions pré-computadas. Substitui
    ``re.search(r'@end', source[offset:])`` que era O(N) por chamada × N
    chamadas = O(N²) em arquivos ObjC grandes. Custo amortizado: O(log N)
    por chamada após O(N) de precompute.
    """
    idx = bisect.bisect_left(end_positions, offset)
    if idx < len(end_positions):
        return end_positions[idx]
    return None


def _parse_objc(source: str) -> ObjcFileInfo:
    # Imports
    imports: list[str] = []
    for m in _RE_IMPORT.finditer(source):
        imports.append(m.group(1))
    for m in _RE_MODULE_IMPORT.finditer(source):
        imports.append(f"@module:{m.group(1)}")

    symbols: list[ObjcSymbolInfo] = []

    # P-N-018 (REVIEW PR #16): pré-computa offsets de ``@end`` uma única vez.
    # Substitui 3 loops de re.search por binary search em lista ordenada.
    end_positions: list[int] = [m.start() for m in re.finditer(r'@end', source)]

    # P-N-003 (REVIEW PR #16): categories e class extensions casam ANTES de
    # @interface pra que ``@interface Foo (Bar)`` não case primeiro como
    # class sem superclass. Coletamos os ranges dos category-matches pra
    # excluir o passo de @interface (evita double-emission).
    category_ranges: set[int] = set()  # m.start() do header de cada category
    for m in _RE_CATEGORY.finditer(source):
        category_ranges.add(m.start())
        class_name = m.group(1)
        category_name = m.group(2)  # vazio = class extension
        line = source[:m.start()].count("\n") + 1
        if category_name:
            kind = "category"
            display_name = f"{class_name}({category_name})"
            sig = f"@interface {class_name} ({category_name})"
        else:
            # Class extension — adiciona surface privada à classe original.
            # Builder não trata explicitamente; emitimos kind="class_extension"
            # pra distinguir de category nomeada. Visibility default
            # (public) é aceitável aqui já que extension ainda é declarada.
            kind = "class_extension"
            display_name = class_name
            sig = f"@interface {class_name} ()"
        # P-N-018: binary search em vez de re.search(source[m.end():]).
        end_offset = _find_end_after(end_positions, m.end())
        body = None
        if end_offset is not None:
            body = source[m.end():end_offset]
        body_hash = hash_body(body) if body is not None else None
        symbols.append(ObjcSymbolInfo(
            name=display_name,
            kind=kind,
            signature=sig,
            line=line,
            body=body,
            body_hash=body_hash,
        ))

    # @interface — skip positions já cobertas por category/extension.
    for m in _RE_INTERFACE.finditer(source):
        if m.start() in category_ranges:
            continue
        name = m.group(1)
        superclass = m.group(2)
        line = source[:m.start()].count("\n") + 1
        sig = f"@interface {name}" + (f" : {superclass}" if superclass else "")
        # Find body (up to @end). P-N-018: binary search em positions
        # pré-computadas em vez de re.search(source[m.end():]).
        end_offset = _find_end_after(end_positions, m.end())
        body = None
        if end_offset is not None:
            body = source[m.end():end_offset]
        else:
            # P-N-018 (REVIEW PR #16): @end ausente → parsing truncado/malformed.
            # Logged DEBUG pra forensics; body permanece None deterministicamente.
            _log.debug("@end ausente para @interface %s na linha %d", name, line)
        # P-N-002 (REVIEW PR #16): ``is not None`` em vez de truthiness pra
        # alinhar com parser_java e preservar empty body (``@interface Foo\n@end``)
        # como hash distinto em vez de cair pra None.
        body_hash = hash_body(body) if body is not None else None
        symbols.append(ObjcSymbolInfo(
            name=name,
            kind="class",
            signature=sig,
            line=line,
            body=body,
            body_hash=body_hash,
        ))

    # @protocol — L-007 + H-009 (REVIEW v1.3.0): popula ``signature`` e
    # ``body_hash`` pra paridade com @interface.
    for m in _RE_PROTOCOL.finditer(source):
        name = m.group(1)
        line = source[:m.start()].count("\n") + 1
        # P-N-018: binary search em positions pré-computadas.
        end_offset = _find_end_after(end_positions, m.end())
        if end_offset is not None:
            body = source[m.end():end_offset]
        else:
            body = None
            _log.debug("@end ausente para @protocol %s na linha %d", name, line)
        # P-N-002 (REVIEW PR #16): truthiness → ``is not None``.
        body_hash = hash_body(body) if body is not None else None
        symbols.append(ObjcSymbolInfo(
            name=name,
            kind="protocol",
            signature=f"@protocol {name}",
            line=line,
            body=body,
            body_hash=body_hash,
        ))

    # @implementation — L-007 + H-009 (REVIEW v1.3.0).
    for m in _RE_IMPLEMENTATION.finditer(source):
        name = m.group(1)
        line = source[:m.start()].count("\n") + 1
        # P-N-018: binary search em positions pré-computadas.
        end_offset = _find_end_after(end_positions, m.end())
        if end_offset is not None:
            body = source[m.end():end_offset]
        else:
            body = None
            _log.debug("@end ausente para @implementation %s na linha %d", name, line)
        # P-N-002 (REVIEW PR #16): truthiness → ``is not None``.
        body_hash = hash_body(body) if body is not None else None
        symbols.append(ObjcSymbolInfo(
            name=name,
            kind="implementation",
            signature=f"@implementation {name}",
            line=line,
            body=body,
            body_hash=body_hash,
        ))

    # Methods — C-002 + L-003 (REVIEW v1.3.0).
    # Estratégia: _RE_METHOD_HEADER captura toda a header até ``{`` ou ``;``.
    # Selector composto é reconstruído por _RE_SEL_SEGMENT (todos os labels:),
    # caindo de volta no primeiro identifier se o método não tiver
    # argumentos (e.g., ``- (NSString *)displayName``). L-003 ancora
    # ``^[+-]\s*\(`` exigindo ``(`` imediatamente após o prefixo, então
    # comentários ``// - here's a note`` não casam.
    for m in _RE_METHOD_HEADER.finditer(source):
        is_class = m.group(1) == "+"
        ret_type = (m.group(2) or "void").strip()
        rest = m.group(3)

        sel_parts = _RE_SEL_SEGMENT.findall(rest)
        if sel_parts:
            # Selector composto: ``label1:label2:label3:``
            full_sel = ":".join(sel_parts) + ":"
        else:
            # No-argument method — o primeiro identifier é o selector.
            head_m = re.match(r'\s*(\w+)', rest)
            if head_m is None:
                continue
            full_sel = head_m.group(1)

        line = source[:m.start()].count("\n") + 1
        prefix = "+" if is_class else "-"
        sig = f"{prefix} ({ret_type}){full_sel}"

        # Body extraction via brace matching. P-N-001 (REVIEW PR #16): com o
        # regex usando lookahead pro ``{``/``;``, ``m.end()`` aponta PRO
        # ``{`` (ou ``;``). ``find_opening_brace`` skipa whitespace e retorna
        # o offset do ``{`` quando presente, ou None pra header terminando
        # em ``;`` (forward decl).
        brace_offset = find_opening_brace(source, m.end())
        body = None
        if brace_offset is not None:
            body = extract_function_body(source, brace_offset, language="objc")
        # P-N-002 (REVIEW PR #16): truthiness ``if body`` cai pra None com
        # body vazio (``{}``) — inconsistente com parser_java (linha 190).
        # ``is not None`` preserva empty body como hash distinto.
        body_hash = hash_body(body) if body is not None else None

        symbols.append(ObjcSymbolInfo(
            name=full_sel,
            kind="method",
            is_class_method=is_class,
            signature=sig,
            line=line,
            body=body,
            body_hash=body_hash,
        ))

    # Properties
    for m in _RE_PROPERTY.finditer(source):
        prop_type = m.group(1)
        prop_name = m.group(2)
        line = source[:m.start()].count("\n") + 1
        symbols.append(ObjcSymbolInfo(
            name=prop_name,
            kind="property",
            signature=f"{prop_type} {prop_name}",
            line=line,
        ))

    return ObjcFileInfo(imports=imports, symbols=symbols)
