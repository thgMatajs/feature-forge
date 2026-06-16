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

from engine.graph.kinds import (
    KIND_BINDING_ACTION,
    KIND_BINDING_VARIABLE,
    KIND_CLASS_REF,
    KIND_COLOR_RESOURCE,
    KIND_STRING_RESOURCE,
    KIND_VIEW_ID,
)

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
#
# P-N-006 (REVIEW PR #16): adicionados ``font``, ``menu``, ``navigation``,
# ``raw``, ``xml``, ``transition``, ``interpolator``, ``attr``, ``id`` —
# todos resource types válidos no Android moderno. ``navigation`` é
# universal em Nav Component; ``font`` cobre Downloadable Fonts;
# ``transition`` cobre Activity Transitions; ``attr`` cobre custom
# attributes em ``styles.xml``; ``id`` cobre forward-declared IDs.
_RESOURCE_PREFIXES = (
    "string", "color", "dimen", "drawable", "mipmap", "layout",
    "anim", "style", "plurals", "integer", "bool", "array",
    # P-N-006 additions:
    "font", "menu", "navigation", "raw", "xml", "transition",
    "interpolator", "attr", "id",
)
_RES_RE = re.compile(
    r'@(?:android:)?(' + '|'.join(_RESOURCE_PREFIXES) + r')/([\w_]+)'
)

# P-N-018 / codereviewbot parser_xml:109 (REVIEW PR #16): layout heuristic
# fallback — root tag conhecida como ViewGroup/View Compose também sinaliza
# layout, mesmo quando path não tem ``/layout/``. Lista canônica de tags
# Android layout roots (não exaustiva, mas cobre 95%+ dos casos reais).
_LAYOUT_ROOT_TAGS = frozenset({
    "LinearLayout",
    "RelativeLayout",
    "FrameLayout",
    "ConstraintLayout",
    "CoordinatorLayout",
    "ScrollView",
    "HorizontalScrollView",
    "GridLayout",
    "TableLayout",
    "merge",
    "include",
    "layout",  # data binding root
    "androidx.constraintlayout.widget.ConstraintLayout",
    "androidx.coordinatorlayout.widget.CoordinatorLayout",
    "androidx.recyclerview.widget.RecyclerView",
    "androidx.viewpager.widget.ViewPager",
    "androidx.viewpager2.widget.ViewPager2",
    "androidx.swiperefreshlayout.widget.SwipeRefreshLayout",
    "androidx.appcompat.widget.Toolbar",
    "com.google.android.material.appbar.AppBarLayout",
    "com.google.android.material.bottomnavigation.BottomNavigationView",
})
_RE_FIRST_TAG = re.compile(r'<\s*([\w\.]+)', re.MULTILINE)

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
    # H-007 (REVIEW v1.3.0): True quando ``binding_action`` é
    # invocação (``::method`` ou ``-> lambda()``); False pra property
    # reads (``@{viewModel.userName}``). Encode no dataclass pra
    # downstream queries filtrarem por intenção sem reparse do ``name``.
    is_method_call: bool = False


@dataclass
class XmlFileInfo:
    is_layout: bool
    is_resources: bool
    symbols: list[XmlSymbolInfo]
    imports: list[str]  # class references → treated as edges
    resource_keys: list[str]  # @string/foo etc.
    binding_variables: list[tuple[str, str]]  # (name, type)


def parse_xml_file(path: Path) -> XmlFileInfo:
    # H-001 (REVIEW v1.3.0): ``errors="replace"`` alinha com parser_kotlin /
    # parser_swift — XML mal-formado em bytes não trava o builder.
    source = path.read_text(encoding="utf-8", errors="replace")
    return _parse_xml(source, path)


def _parse_xml(source: str, path: Path) -> XmlFileInfo:
    symbols: list[XmlSymbolInfo] = []
    # P-N-014 / codereviewbot parser_xml:81 (REVIEW PR #16): class_refs era
    # list — refs duplicados (tag class + attr class do mesmo FQ) passavam
    # pelo persist sem unique constraint, inflando ``imports`` table. Set
    # dedup mantém first-seen-order via sorted() no return.
    class_refs_set: set[str] = set()
    resource_keys: list[str] = []
    binding_vars: list[tuple[str, str]] = []

    path_str = str(path)
    # Resources detection — combina heurística de path com tag raiz <resources>,
    # cobrindo fixtures que não sigam a convenção `res/values/`.
    is_resources = bool(_RE_RESOURCES_ROOT.search(source)) or (
        "values" in path_str
        and path.name in ("strings.xml", "colors.xml", "dimens.xml", "themes.xml")
    )
    # Layout heurística — path-based primeiro, fallback em root tag.
    # P-N-018 / codereviewbot parser_xml:109 (REVIEW PR #16): arquivos
    # com tag root ViewGroup/Compose mesmo sem ``/layout/`` no path agora
    # casam (layouts custom em test fixtures, projetos com convenções
    # alternativas).
    is_layout = (not is_resources) and (
        "/layout/" in path_str or "\\layout\\" in path_str
    )
    if not is_resources and not is_layout:
        first_tag_m = _RE_FIRST_TAG.search(source)
        if first_tag_m and first_tag_m.group(1) in _LAYOUT_ROOT_TAGS:
            is_layout = True

    if is_resources:
        # Resource files: extract string/color keys
        for m in _RE_STRING_RESOURCE.finditer(source):
            line = source[:m.start()].count("\n") + 1
            symbols.append(XmlSymbolInfo(
                name=m.group(1),
                kind=KIND_STRING_RESOURCE,  # P-N-021 (REVIEW PR #16)
                line=line,
            ))
        for m in _RE_COLOR_RESOURCE.finditer(source):
            line = source[:m.start()].count("\n") + 1
            symbols.append(XmlSymbolInfo(
                name=m.group(1),
                kind=KIND_COLOR_RESOURCE,  # P-N-021
                line=line,
            ))

    if is_layout:
        # View IDs
        for m in _RE_VIEW_ID.finditer(source):
            line = source[:m.start()].count("\n") + 1
            symbols.append(XmlSymbolInfo(
                name=m.group(1),
                kind=KIND_VIEW_ID,  # P-N-021
                line=line,
            ))

        # Tag names as class references
        for m in _RE_TAG_CLASS.finditer(source):
            class_name = m.group(1)
            line = source[:m.start()].count("\n") + 1
            symbols.append(XmlSymbolInfo(
                name=class_name,
                kind=KIND_CLASS_REF,  # P-N-021
                line=line,
            ))
            class_refs_set.add(class_name)

        # Attribute class references
        for m in _RE_ATTR_CLASS.finditer(source):
            class_name = m.group(1)
            class_refs_set.add(class_name)

        # Data binding variables
        for m in _RE_BINDING_VAR.finditer(source):
            var_name = m.group(1)
            var_type = m.group(2)
            line = source[:m.start()].count("\n") + 1
            symbols.append(XmlSymbolInfo(
                name=var_name,
                kind=KIND_BINDING_VARIABLE,  # P-N-021
                line=line,
                context=var_type,
            ))
            binding_vars.append((var_name, var_type))
            class_refs_set.add(var_type)

        # Resource references in layout
        for m in _RES_RE.finditer(source):
            res_key = f"{m.group(1)}/{m.group(2)}"
            resource_keys.append(res_key)

        # Binding actions (@{...}) — H-007 (REVIEW v1.3.0): registra TODOS,
        # tanto invocações (``::method``, ``-> lambda()``) quanto property
        # reads (``@{viewModel.userName}``). Property reads são bindings
        # legítimos no Android data binding (one-way / two-way). Flag
        # ``is_method_call`` permite que queries downstream filtrem por
        # intenção sem perder cobertura.
        for m in _RE_BINDING_EXPR.finditer(source):
            expr = m.group(1).strip()
            is_method_call = ("::" in expr) or ("->" in expr) or ("(" in expr)
            line = source[:m.start()].count("\n") + 1
            symbols.append(XmlSymbolInfo(
                name=expr,
                kind=KIND_BINDING_ACTION,  # P-N-021
                line=line,
                is_method_call=is_method_call,
            ))

    return XmlFileInfo(
        is_layout=is_layout,
        is_resources=is_resources,
        symbols=symbols,
        # Sorted pra determinismo cross-platform.
        imports=sorted(class_refs_set),
        resource_keys=resource_keys,
        binding_variables=binding_vars,
    )


__all__ = [
    "XmlSymbolInfo",
    "XmlFileInfo",
    "parse_xml_file",
]
