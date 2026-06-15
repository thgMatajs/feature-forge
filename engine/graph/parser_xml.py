"""XML parser for Android layouts and resources.

Extracts view IDs, referenced classes, data binding variables, resource
keys, and binding action references from Android XML files.

This is a regex-based parser — sufficient for the structured, predictable
format of Android XML. No full XML AST needed.

XML symbols não têm `{}`-body (NÃO aplicável); ``body_hash``/``body_tokens``
NULL pra todos os símbolos. Por isso este parser não consome
``engine.graph._body_text``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# View ID: @+id/foo, @id/foo, @android:id/foo
_RE_VIEW_ID = re.compile(r'@(?:\+)?(?:android:)?id/([\w_]+)')

# Fully-qualified class reference in tag names
_RE_TAG_CLASS = re.compile(r'<([a-z][\w.]+\.[A-Z]\w+(?:\.\w+)*)')

# android:name / class= attributes
_RE_ATTR_CLASS = re.compile(
    r'(?:android:name|class)\s*=\s*"([\w.]+(?:\.[A-Z]\w+)+)"'
)

# Data binding: <variable name="..." type="..." />
_RE_BINDING_VAR = re.compile(
    r'<variable\s+name="(\w+)"\s+type="([\w.]+(?:\.[A-Z]\w+)+)"\s*/>'
)

# Resource references: @string/foo, @color/bar, @dimen/baz, etc.
_RESOURCE_PREFIXES = (
    "string", "color", "dimen", "drawable", "mipmap", "layout",
    "anim", "style", "plurals", "integer", "bool", "array",
)
_RES_RE = re.compile(
    r'@(?:android:)?(' + '|'.join(_RESOURCE_PREFIXES) + r')/([\w_]+)'
)

# Data binding expression: @{viewModel.property}, @{viewModel::method}
_RE_BINDING_EXPR = re.compile(r'@\{([^}]+)\}')

# <string name="key">value</string> (resources files)
_RE_STRING_RESOURCE = re.compile(
    r'<string\s+name="([\w_]+)"[^>]*>(.*?)</string>', re.DOTALL
)

# <color name="key">#hex</color>
_RE_COLOR_RESOURCE = re.compile(r'<color\s+name="([\w_]+)">(.*?)</color>')

# Root <resources> tag — sinaliza arquivo de resources (mais robusto que path-based).
_RE_RESOURCES_ROOT = re.compile(r'<\s*resources(?:\s[^>]*)?>')


@dataclass
class XmlSymbolInfo:
    name: str
    # "view_id" | "class_ref" | "binding_variable" | "resource_key"
    # | "binding_action" | "string_resource" | "color_resource"
    kind: str
    line: int = 0
    context: Optional[str] = None  # e.g., tag name for view IDs


@dataclass
class XmlFileInfo:
    is_layout: bool
    is_resources: bool
    symbols: list[XmlSymbolInfo]
    imports: list[str]  # class references → treated as edges
    resource_keys: list[str]  # @string/foo etc.
    binding_variables: list[tuple[str, str]]  # (name, type)


def parse_xml_file(path: Path) -> XmlFileInfo:
    source = path.read_text(encoding="utf-8")
    return _parse_xml(source, path)


def _parse_xml(source: str, path: Path) -> XmlFileInfo:
    symbols: list[XmlSymbolInfo] = []
    class_refs: list[str] = []
    resource_keys: list[str] = []
    binding_vars: list[tuple[str, str]] = []

    path_str = str(path)
    # Resources detection — combina heurística de path com tag raiz <resources>,
    # cobrindo fixtures que não sigam a convenção `res/values/`.
    is_resources = bool(_RE_RESOURCES_ROOT.search(source)) or (
        "values" in path_str
        and path.name in ("strings.xml", "colors.xml", "dimens.xml", "themes.xml")
    )
    # Layout heurística — path-based; um arquivo nunca é layout E resources.
    is_layout = (not is_resources) and (
        "/layout/" in path_str or "\\layout\\" in path_str
    )

    if is_resources:
        # Resource files: extract string/color keys
        for m in _RE_STRING_RESOURCE.finditer(source):
            line = source[:m.start()].count("\n") + 1
            symbols.append(XmlSymbolInfo(
                name=m.group(1),
                kind="string_resource",
                line=line,
            ))
        for m in _RE_COLOR_RESOURCE.finditer(source):
            line = source[:m.start()].count("\n") + 1
            symbols.append(XmlSymbolInfo(
                name=m.group(1),
                kind="color_resource",
                line=line,
            ))

    if is_layout:
        # View IDs
        for m in _RE_VIEW_ID.finditer(source):
            line = source[:m.start()].count("\n") + 1
            symbols.append(XmlSymbolInfo(
                name=m.group(1),
                kind="view_id",
                line=line,
            ))

        # Tag names as class references
        for m in _RE_TAG_CLASS.finditer(source):
            class_name = m.group(1)
            line = source[:m.start()].count("\n") + 1
            symbols.append(XmlSymbolInfo(
                name=class_name,
                kind="class_ref",
                line=line,
            ))
            class_refs.append(class_name)

        # Attribute class references
        for m in _RE_ATTR_CLASS.finditer(source):
            class_name = m.group(1)
            class_refs.append(class_name)

        # Data binding variables
        for m in _RE_BINDING_VAR.finditer(source):
            var_name = m.group(1)
            var_type = m.group(2)
            line = source[:m.start()].count("\n") + 1
            symbols.append(XmlSymbolInfo(
                name=var_name,
                kind="binding_variable",
                line=line,
                context=var_type,
            ))
            binding_vars.append((var_name, var_type))
            class_refs.append(var_type)

        # Resource references in layout
        for m in _RES_RE.finditer(source):
            res_key = f"{m.group(1)}/{m.group(2)}"
            resource_keys.append(res_key)

        # Binding actions (@{...}) — only expressions with method invocation
        # or lambda arrow (heuristic: skip pure property reads like
        # `@{viewModel.userName}`).
        for m in _RE_BINDING_EXPR.finditer(source):
            expr = m.group(1).strip()
            if "::" in expr or "->" in expr:
                line = source[:m.start()].count("\n") + 1
                symbols.append(XmlSymbolInfo(
                    name=expr,
                    kind="binding_action",
                    line=line,
                ))

    return XmlFileInfo(
        is_layout=is_layout,
        is_resources=is_resources,
        symbols=symbols,
        imports=class_refs,
        resource_keys=resource_keys,
        binding_variables=binding_vars,
    )


__all__ = [
    "XmlSymbolInfo",
    "XmlFileInfo",
    "parse_xml_file",
]
