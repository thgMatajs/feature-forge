"""Centralized kind constants for graph symbols.

Defines canonical kind strings used in ``symbols.kind`` column. Prevents
typo-driven drift across parser/persist modules — quem grava em
``symbols.kind`` deve consumir destes constants em vez de string literal.

**Status (v1.3.0):** módulo criado mas parsers ainda usam literais. O
refactor pra consumir estes constants fica como follow-up (registrado
em ``docs/design/04-pending.md``), pra evitar conflito com edits
concorrentes em ``parser_{java,xml,objc}.py``.

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

# ── Objective-C (prefixed per `_persist_objc` convention) ───────────────────

KIND_OBJC_CLASS = "objc_class"
KIND_OBJC_PROTOCOL = "objc_protocol"
KIND_OBJC_IMPLEMENTATION = "objc_implementation"
KIND_OBJC_METHOD = "objc_method"
KIND_OBJC_PROPERTY = "objc_property"

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
    # ObjC
    "KIND_OBJC_CLASS",
    "KIND_OBJC_PROTOCOL",
    "KIND_OBJC_IMPLEMENTATION",
    "KIND_OBJC_METHOD",
    "KIND_OBJC_PROPERTY",
    # XML
    "KIND_VIEW_ID",
    "KIND_CLASS_REF",
    "KIND_BINDING_VARIABLE",
    "KIND_BINDING_ACTION",
    "KIND_RESOURCE_KEY",
    "KIND_STRING_RESOURCE",
    "KIND_COLOR_RESOURCE",
]
