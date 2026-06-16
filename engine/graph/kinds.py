"""Centralized kind constants for graph symbols.

Defines canonical kind strings used in ``symbols.kind`` column. Prevents
typo-driven drift across parser/persist modules — quem grava em
``symbols.kind`` deve consumir destes constants em vez de string literal.

**Status (P-N-021 / REVIEW PR #16, v1.3.0):** parsers ObjC e XML
consomem estes constants em vez de literais. Java/Kotlin/Swift/TS
adotam progressivamente — kinds parametrizados (composable_fun,
sealed_class, etc.) ainda permanecem como literais nos parsers que os
sintetizam dinamicamente.

Refs:
- engine/graph/builder.py ``_persist_*`` functions (kinds usados em INSERTs)
- engine/graph/parser_{java,xml,objc,kotlin,swift}.py (kinds emitidos)
- docs/schemas/graph.md (canonical kind vocabulary)
"""

# ── Generic (cross-language) ────────────────────────────────────────────────

KIND_CLASS = "class"
KIND_INTERFACE = "interface"
KIND_METHOD = "method"
KIND_FUNCTION = "function"
KIND_PROPERTY = "property"
KIND_CONSTRUCTOR = "constructor"
KIND_ANNOTATION = "annotation"
KIND_ENUM = "enum"
KIND_RECORD = "record"

# ── Objective-C (raw kinds emitted by parser_objc; builder adds ``objc_`` prefix) ─

# IMPORTANTE: parser_objc emite kinds CRUS (sem prefix). O prefix
# ``objc_`` é adicionado em ``builder._persist_objc`` via
# ``f\"objc_{s.kind}\"``. As constants abaixo são pré-prefix, alinhadas
# com o que o parser produz.

KIND_OBJC_RAW_CLASS = "class"
KIND_OBJC_RAW_PROTOCOL = "protocol"
KIND_OBJC_RAW_IMPLEMENTATION = "implementation"
KIND_OBJC_RAW_METHOD = "method"
KIND_OBJC_RAW_PROPERTY = "property"
KIND_OBJC_RAW_CATEGORY = "category"
KIND_OBJC_RAW_CLASS_EXTENSION = "class_extension"

# Post-prefix (após builder._persist_objc.f\"objc_{kind}\") — pra consumers
# downstream que lêem do schema sqlite.
KIND_OBJC_CLASS = "objc_class"
KIND_OBJC_PROTOCOL = "objc_protocol"
KIND_OBJC_IMPLEMENTATION = "objc_implementation"
KIND_OBJC_METHOD = "objc_method"
KIND_OBJC_PROPERTY = "objc_property"
KIND_OBJC_CATEGORY = "objc_category"
KIND_OBJC_CLASS_EXTENSION = "objc_class_extension"

# ── XML-specific ────────────────────────────────────────────────────────────

KIND_VIEW_ID = "view_id"
KIND_CLASS_REF = "class_ref"
KIND_BINDING_VARIABLE = "binding_variable"
KIND_BINDING_ACTION = "binding_action"
KIND_RESOURCE_KEY = "resource_key"
KIND_STRING_RESOURCE = "string_resource"
KIND_COLOR_RESOURCE = "color_resource"


__all__ = [
    # Generic
    "KIND_CLASS",
    "KIND_INTERFACE",
    "KIND_METHOD",
    "KIND_FUNCTION",
    "KIND_PROPERTY",
    "KIND_CONSTRUCTOR",
    "KIND_ANNOTATION",
    "KIND_ENUM",
    "KIND_RECORD",
    # ObjC raw (parser-emitted, pre-prefix)
    "KIND_OBJC_RAW_CLASS",
    "KIND_OBJC_RAW_PROTOCOL",
    "KIND_OBJC_RAW_IMPLEMENTATION",
    "KIND_OBJC_RAW_METHOD",
    "KIND_OBJC_RAW_PROPERTY",
    "KIND_OBJC_RAW_CATEGORY",
    "KIND_OBJC_RAW_CLASS_EXTENSION",
    # ObjC post-prefix (downstream consumers)
    "KIND_OBJC_CLASS",
    "KIND_OBJC_PROTOCOL",
    "KIND_OBJC_IMPLEMENTATION",
    "KIND_OBJC_METHOD",
    "KIND_OBJC_PROPERTY",
    "KIND_OBJC_CATEGORY",
    "KIND_OBJC_CLASS_EXTENSION",
    # XML
    "KIND_VIEW_ID",
    "KIND_CLASS_REF",
    "KIND_BINDING_VARIABLE",
    "KIND_BINDING_ACTION",
    "KIND_RESOURCE_KEY",
    "KIND_STRING_RESOURCE",
    "KIND_COLOR_RESOURCE",
]
