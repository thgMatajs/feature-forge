"""Simplified Objective-C parser — imports + symbols only.

NO call graph (``[obj selector]`` parsing). NO full AST. Regex-based,
best-effort. Covers the most common patterns found in iOS legacy code.

This is sufficient for graph queries (Q4 symbols, Q11/12/13 dup detection
via body_hash) without the complexity of a full ObjC AST walker.
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

_RE_IMPORT = re.compile(r'^#import\s+[<"]([^>"]+)[>"]', re.MULTILINE)
_RE_MODULE_IMPORT = re.compile(r'^@import\s+(\w+)\s*;', re.MULTILINE)

_RE_INTERFACE = re.compile(
    r'@interface\s+(\w+)\s*(?::\s*(\w+(?:\s*<\w+>)?))?',
    re.MULTILINE,
)
_RE_PROTOCOL = re.compile(r'@protocol\s+(\w+)', re.MULTILINE)
_RE_IMPLEMENTATION = re.compile(r'@implementation\s+(\w+)', re.MULTILINE)

# Method: - (void)methodName or + (instancetype)methodName:(type)param
_RE_METHOD = re.compile(
    r'^([+-])\s*'
    r'(?:\(([\w\s\*<>,\[\]{}]+)\))?\s*'  # return type in parens
    r'(\w+)\s*'  # method name / first segment
    r'(?::\s*\(([\w\s\*<>]+)\)\s*(\w+)\s*)?'  # optional first param
    r'(?:\s*(?:\w+)\s*:\s*\(([\w\s\*<>]+)\)\s*(\w+)\s*)*',  # more params
    re.MULTILINE,
)

_RE_PROPERTY = re.compile(
    r'@property\s*(?:\([^)]*\))?\s*'
    r'(\w+(?:\s*\*)?)\s+'  # type
    r'(\w+)\s*;',  # name
    re.MULTILINE,
)


@dataclass
class ObjcSymbolInfo:
    name: str
    kind: str  # "class" | "protocol" | "implementation" | "method" | "property"
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
    source = path.read_text(encoding="utf-8")
    return _parse_objc(source)


def _parse_objc(source: str) -> ObjcFileInfo:
    # Imports
    imports: list[str] = []
    for m in _RE_IMPORT.finditer(source):
        imports.append(m.group(1))
    for m in _RE_MODULE_IMPORT.finditer(source):
        imports.append(f"@module:{m.group(1)}")

    symbols: list[ObjcSymbolInfo] = []

    # @interface
    for m in _RE_INTERFACE.finditer(source):
        name = m.group(1)
        superclass = m.group(2)
        line = source[:m.start()].count("\n") + 1
        sig = f"@interface {name}" + (f" : {superclass}" if superclass else "")
        # Find body (up to @end)
        end_m = re.search(r'@end', source[m.end():])
        body = None
        if end_m:
            body = source[m.end():m.end() + end_m.start()]
        body_hash = hash_body(body) if body else None
        symbols.append(ObjcSymbolInfo(
            name=name,
            kind="class",
            signature=sig,
            line=line,
            body=body,
            body_hash=body_hash,
        ))

    # @protocol
    for m in _RE_PROTOCOL.finditer(source):
        name = m.group(1)
        line = source[:m.start()].count("\n") + 1
        end_m = re.search(r'@end', source[m.end():])
        body = source[m.end():m.end() + end_m.start()] if end_m else None
        symbols.append(ObjcSymbolInfo(
            name=name,
            kind="protocol",
            line=line,
            body=body,
        ))

    # @implementation
    for m in _RE_IMPLEMENTATION.finditer(source):
        name = m.group(1)
        line = source[:m.start()].count("\n") + 1
        end_m = re.search(r'@end', source[m.end():])
        body = source[m.end():m.end() + end_m.start()] if end_m else None
        symbols.append(ObjcSymbolInfo(
            name=name,
            kind="implementation",
            line=line,
            body=body,
        ))

    # Methods (simplified — best effort)
    for m in _RE_METHOD.finditer(source):
        is_class = m.group(1) == "+"
        ret_type = m.group(2) or "void"
        sel_parts = [m.group(3)]
        if m.group(4) and m.group(5):
            sel_parts.append(f"{m.group(3)}:{m.group(5)}")
        full_sel = ":".join(sel_parts)
        line = source[:m.start()].count("\n") + 1
        prefix = "+" if is_class else "-"
        sig = f"{prefix} ({ret_type}){full_sel}"

        # Body extraction via brace matching
        brace_offset = find_opening_brace(source, m.end())
        body = None
        if brace_offset is not None:
            body = extract_function_body(source, brace_offset, language="objc")
        body_hash = hash_body(body) if body else None

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
