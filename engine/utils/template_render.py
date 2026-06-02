"""Minimal Mustache-like template renderer for feature-intake stubs.

Used by ``engine/evolve.py`` when applying refactor-style proposals (the
reuse-intelligence handlers) to render the canonical
``templates/feature-intake-refactor.template.md`` skeleton with the
proposal's payload values.

Capabilities:
- ``{{var}}`` — variable substitution
- ``{{var | "fallback"}}`` — fallback when var is missing/empty
- Unknown / missing placeholders stay as literal ``{{var}}`` so callers can
  spot them during manual review.

No conditionals, no loops, no escaping — intentionally tiny. Callers
pre-render dynamic blocks (e.g., bullet lists of locations) as plain strings
before substitution.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

_RE_VAR = re.compile(
    r"""\{\{\s*
        (?P<key>[A-Za-z_][A-Za-z0-9_]*)
        (?:\s*\|\s*(?P<fallback>"[^"]*"|'[^']*'))?
        \s*\}\}""",
    re.VERBOSE,
)


def render_template(
    template_text: str,
    context: Mapping[str, Any],
) -> str:
    """Replace ``{{var}}`` placeholders in ``template_text`` using ``context``.

    A missing or ``None`` value falls back to the inline ``| "default"`` token
    when present; otherwise the original placeholder is left intact so the
    user can see what needs filling.
    """
    def _sub(match: re.Match) -> str:
        key = match.group("key")
        fallback_token = match.group("fallback") or ""
        value = context.get(key)
        if value is None or value == "":
            if fallback_token:
                return fallback_token.strip().strip('"').strip("'")
            return match.group(0)
        return str(value)

    return _RE_VAR.sub(_sub, template_text)


def render_template_file(
    template_path: Path,
    context: Mapping[str, Any],
) -> str:
    """Read ``template_path`` and run ``render_template``. UTF-8 only."""
    text = template_path.read_text(encoding="utf-8")
    return render_template(text, context)


__all__ = [
    "render_template",
    "render_template_file",
]
