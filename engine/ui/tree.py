"""ASCII tree renderer.

Renders nested dicts / lists / tuples as a left-aligned tree using
└─ and ├─ box-drawing chars. Used by `forge status`, `forge graph`,
`forge memory`, and any read-only command that displays hierarchical data.

Conventions:
- dict: each (key, value) becomes a branch; the key is the label.
- list/tuple: each item becomes a numbered branch ("[0]", "[1]"…).
- scalar (str/int/bool/None): leaf, printed inline next to the parent label.

Caller can pre-format leaves themselves (e.g., colour, status icons) — the
tree renderer treats strings opaquely.
"""

from __future__ import annotations

from typing import Any

_BRANCH = "├─ "
_LAST = "└─ "
_PIPE = "│  "
_GAP = "   "


def render_tree(root: Any, *, label: str | None = None) -> str:
    """Render an arbitrary nested structure as a tree string.

    If `label` is given, it's the root line (e.g., feature slug). Otherwise
    the structure is rendered without a header.
    """
    lines: list[str] = []
    if label is not None:
        lines.append(label)
    _render(root, prefix="", out=lines)
    return "\n".join(lines)


def _is_container(value: Any) -> bool:
    return isinstance(value, (dict, list, tuple))


def _render(value: Any, *, prefix: str, out: list[str]) -> None:
    if isinstance(value, dict):
        items = list(value.items())
        last_idx = len(items) - 1
        for idx, (key, child) in enumerate(items):
            connector = _LAST if idx == last_idx else _BRANCH
            if _is_container(child):
                out.append(f"{prefix}{connector}{key}")
                next_prefix = prefix + (_GAP if idx == last_idx else _PIPE)
                _render(child, prefix=next_prefix, out=out)
            else:
                out.append(f"{prefix}{connector}{key}: {_format_scalar(child)}")
    elif isinstance(value, (list, tuple)):
        last_idx = len(value) - 1
        for idx, child in enumerate(value):
            connector = _LAST if idx == last_idx else _BRANCH
            if _is_container(child):
                out.append(f"{prefix}{connector}[{idx}]")
                next_prefix = prefix + (_GAP if idx == last_idx else _PIPE)
                _render(child, prefix=next_prefix, out=out)
            else:
                out.append(f"{prefix}{connector}[{idx}] {_format_scalar(child)}")
    else:
        # Scalar at root — just append it.
        out.append(f"{prefix}{_format_scalar(value)}")


def _format_scalar(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)
