"""Card contribution merger.

Collects `contributes:` blocks from every activated card and turns them into a
single `MergedContributions` payload. Then renders templates by applying merge
modes (`append-section`, `replace-section`, `before-section`, `after-section`,
`merge-keys`).

Determinism (per `card.md §Resolution order`):

1. Group contributions by target/extension-point/event.
2. Sort each group by `(merge_order, card_name)` — `merge_order` defaults to 50.
3. Apply each contribution in order.

`config-defaults` carry their producer card to surface duplicates as warnings
on the result.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ..utils.yaml_io import YamlIOError, read_yaml
from . import CardError
from .loader import CardManifest

_DEFAULT_MERGE_ORDER = 50

# Heading regex — `# Title`, `## Title`, etc. Up to 6 `#` per markdown spec.
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")

# Setext underline regex — `===` (H1) or `---` (H2) on a line by itself.
_SETEXT_UNDERLINE_RE = re.compile(r"^(=+|-+)\s*$")


def _match_heading(lines: list[str], idx: int) -> tuple[int, str] | None:
    """Return (level, title) when `lines[idx]` is a heading (ATX or setext).

    ATX form: `# Title`, `## Title`, ... — single line.
    Setext form: `Title\n===` (H1) or `Title\n---` (H2) — two lines, where the
    underline is `=`/`-` only. Setext detection consumes `lines[idx]` as the
    title; the underline lives at `lines[idx + 1]`.
    """
    line = lines[idx]
    m = _HEADING_RE.match(line)
    if m:
        return len(m.group(1)), m.group(2).strip()
    # Setext: `lines[idx]` is the title, `lines[idx + 1]` is the underline.
    if idx + 1 >= len(lines):
        return None
    underline = lines[idx + 1]
    if not _SETEXT_UNDERLINE_RE.match(underline):
        return None
    title = line.strip()
    if not title:
        return None
    level = 1 if underline.startswith("=") else 2
    return level, title


@dataclass
class MergedContributions:
    """Aggregated contributions across all activated cards.

    Each list/dict carries `card_name` so downstream errors trace back to the
    contributor.
    """

    templates: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    validators: list[dict[str, Any]] = field(default_factory=list)
    agent_prompts: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    hooks: list[dict[str, Any]] = field(default_factory=list)
    config_defaults: dict[str, str] = field(default_factory=dict)
    config_defaults_sources: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


# ── Public API ───────────────────────────────────────────────────────────────


def merge_contributions(activated: list[CardManifest]) -> MergedContributions:
    """Walk every activated card's `contributes:` block and group entries."""
    merged = MergedContributions()

    for card in activated:
        contribs = card.contributes or {}

        for tmpl in contribs.get("templates") or []:
            target = tmpl.get("target")
            if not target:
                continue
            entry = {
                "section": tmpl.get("section"),
                "file": tmpl.get("file"),
                "merge": tmpl.get("merge") or "append-section",
                "merge_order": int(tmpl.get("merge-order", _DEFAULT_MERGE_ORDER)),
                "card_name": card.name,
                "card_source": card.source_path,
            }
            merged.templates.setdefault(target, []).append(entry)

        for v in contribs.get("validators") or []:
            merged.validators.append(
                {
                    "name": v.get("name"),
                    "file": v.get("file"),
                    "runs_on": list(v.get("runs-on") or []),
                    "severity": v.get("severity", "warn"),
                    "description": v.get("description"),
                    "card_name": card.name,
                    "card_source": card.source_path,
                }
            )

        for p in contribs.get("agent-prompts") or []:
            agent = p.get("inject-into")
            if not agent:
                continue
            merged.agent_prompts.setdefault(agent, []).append(
                {
                    "extension_point": p.get("extension-point"),
                    "file": p.get("file"),
                    "merge_order": int(p.get("merge-order", _DEFAULT_MERGE_ORDER)),
                    "card_name": card.name,
                    "card_source": card.source_path,
                }
            )

        for h in contribs.get("hooks") or []:
            merged.hooks.append(
                {
                    "file": h.get("file"),
                    "events": list(h.get("events") or []),
                    "glob": h.get("glob"),
                    "events_mapping": dict(h.get("events-mapping") or {}),
                    "card_name": card.name,
                    "card_source": card.source_path,
                }
            )

        for key, value in (contribs.get("config-defaults") or {}).items():
            if not isinstance(key, str):
                continue
            if key in merged.config_defaults and merged.config_defaults[key] != value:
                merged.warnings.append(
                    f"CONFIG-DEFAULT-CONFLICT: key {key!r} set by "
                    f"{merged.config_defaults_sources[key]!r}={merged.config_defaults[key]!r} "
                    f"and now by {card.name!r}={value!r}; keeping the first."
                )
                continue
            merged.config_defaults[key] = value
            merged.config_defaults_sources[key] = card.name

    # Sort every group deterministically.
    for target, entries in merged.templates.items():
        entries.sort(key=lambda e: (e["merge_order"], e["card_name"]))
    for agent, entries in merged.agent_prompts.items():
        entries.sort(key=lambda e: (e["merge_order"], e["card_name"]))
    merged.validators.sort(key=lambda v: (v["card_name"], v["name"] or ""))
    merged.hooks.sort(key=lambda h: (h["card_name"], h["file"] or ""))

    return merged


def render_merged_template(
    target_template_path: Path,
    contributions: list[dict[str, Any]],
    output_path: Path,
) -> None:
    """Render the canonical template with all card contributions applied.

    `target_template_path` is the base file in FORGE_HOME/templates/; the
    contributions are applied in order, then the result is written atomically
    to `output_path`.

    Currently supports merge modes:
    - `merge-keys` for YAML targets (top-level key merge with conflict detection)
    - `append-section`, `replace-section`, `before-section`, `after-section`
      for markdown targets (operating on `#`-style headings)
    """
    if not target_template_path.is_file():
        raise CardError(f"target template not found: {target_template_path}")

    is_yaml = target_template_path.suffix in (".yaml", ".yml")

    if is_yaml:
        rendered = _render_yaml(target_template_path, contributions)
    else:
        rendered = _render_markdown(target_template_path, contributions)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = output_path.with_suffix(output_path.suffix + ".tmp")
    tmp.write_text(rendered, encoding="utf-8")
    tmp.replace(output_path)


# ── YAML merge ───────────────────────────────────────────────────────────────


def _render_yaml(target: Path, contributions: list[dict[str, Any]]) -> str:
    try:
        base = read_yaml(target) or {}
    except YamlIOError as exc:
        raise CardError(str(exc)) from exc
    if not isinstance(base, dict):
        raise CardError(
            f"YAML template {target} must have a mapping at top level "
            f"for merge-keys mode (got {type(base).__name__})"
        )

    seen_keys_owner: dict[str, str] = {}
    for contrib in contributions:
        mode = contrib.get("merge") or "merge-keys"
        if mode != "merge-keys":
            raise CardError(
                f"YAML template {target}: merge mode {mode!r} is not supported "
                f"for YAML targets (use merge-keys)"
            )
        fragment_path = contrib["card_source"] / contrib["file"]
        if not fragment_path.is_file():
            raise CardError(
                f"contribution file not found: {fragment_path} "
                f"(from card {contrib['card_name']!r})"
            )
        try:
            fragment = read_yaml(fragment_path) or {}
        except YamlIOError as exc:
            raise CardError(str(exc)) from exc
        if not isinstance(fragment, dict):
            raise CardError(
                f"YAML fragment {fragment_path} must be a mapping at top level"
            )
        for key, value in fragment.items():
            if key in seen_keys_owner and seen_keys_owner[key] != contrib["card_name"]:
                raise CardError(
                    f"YAML merge conflict on key {key!r}: claimed by both "
                    f"{seen_keys_owner[key]!r} and {contrib['card_name']!r}"
                )
            base[key] = value
            seen_keys_owner[key] = contrib["card_name"]

    return yaml.safe_dump(base, default_flow_style=False, sort_keys=False, allow_unicode=True)


# ── Markdown merge ───────────────────────────────────────────────────────────


def _render_markdown(target: Path, contributions: list[dict[str, Any]]) -> str:
    text = target.read_text(encoding="utf-8")
    for contrib in contributions:
        mode = contrib.get("merge") or "append-section"
        section = contrib.get("section")
        fragment_path = contrib["card_source"] / contrib["file"]
        if not fragment_path.is_file():
            raise CardError(
                f"contribution file not found: {fragment_path} "
                f"(from card {contrib['card_name']!r})"
            )
        fragment = fragment_path.read_text(encoding="utf-8").rstrip() + "\n"

        if mode == "append-section":
            text = _md_append_section(text, section, fragment, contrib["card_name"])
        elif mode == "replace-section":
            if not section:
                raise CardError(
                    f"replace-section requires `section:` (card={contrib['card_name']!r})"
                )
            text = _md_replace_section(text, section, fragment, contrib["card_name"])
        elif mode == "before-section":
            if not section:
                raise CardError(
                    f"before-section requires `section:` (card={contrib['card_name']!r})"
                )
            text = _md_insert_relative(text, section, fragment, before=True, card_name=contrib["card_name"])
        elif mode == "after-section":
            if not section:
                raise CardError(
                    f"after-section requires `section:` (card={contrib['card_name']!r})"
                )
            text = _md_insert_relative(text, section, fragment, before=False, card_name=contrib["card_name"])
        else:
            raise CardError(
                f"unsupported merge mode {mode!r} for markdown target {target} "
                f"(card={contrib['card_name']!r})"
            )
    return text


def _is_setext_heading(lines: list[str], idx: int) -> bool:
    """True quando `lines[idx]` é a TÍTULO de uma heading setext (underline em idx+1)."""
    if idx + 1 >= len(lines):
        return False
    if _HEADING_RE.match(lines[idx]):
        return False
    if not lines[idx].strip():
        return False
    return bool(_SETEXT_UNDERLINE_RE.match(lines[idx + 1]))


def _heading_block_end(lines: list[str], idx: int) -> int:
    """Retorna o índice (exclusivo) onde a heading em `idx` termina.

    Pra ATX: `idx + 1` (heading ocupa só 1 linha).
    Pra setext: `idx + 2` (inclui o underline `===` / `---`).

    Garante que ao deletar `lines[:start_of_heading] + lines[block_end:]` o
    underline órfão não sobre.
    """
    if _is_setext_heading(lines, idx):
        return idx + 2
    return idx + 1


def _md_find_section(text: str, section: str) -> tuple[int, int, int] | None:
    """Find a section by title. Returns (start_line, end_line_exclusive, level)
    or None when not found. `end_line` points to the line that starts the next
    heading of equal-or-shallower depth, or past EOF.

    Recognises both ATX (`# Title`) and setext (`Title\\n===`) headings.
    """
    if not section:
        return None
    target = section.strip()
    lines = text.splitlines()
    start = None
    level = None
    for idx in range(len(lines)):
        h = _match_heading(lines, idx)
        if h and h[1] == target:
            start = idx
            level = h[0]
            break
    if start is None:
        return None

    end = len(lines)
    # Skip past the underline when the matched heading is setext.
    scan_from = _heading_block_end(lines, start)
    for idx in range(scan_from, len(lines)):
        h = _match_heading(lines, idx)
        if h and h[0] <= level:
            end = idx
            break
    return start, end, level


def _preserve_trailing_newline(original: str, joined: str) -> str:
    """Preserva (ou remove) `\\n` final conforme o original."""
    had_trailing = original.endswith("\n")
    if had_trailing and not joined.endswith("\n"):
        return joined + "\n"
    if not had_trailing and joined.endswith("\n"):
        return joined.rstrip("\n")
    return joined


def _md_append_section(text: str, section: str | None, fragment: str, card_name: str) -> str:
    """`append-section` — if a `section:` is given and exists, append fragment
    inside it (before the next heading). Otherwise append at EOF.
    """
    if section:
        found = _md_find_section(text, section)
        if found:
            _start, end, _ = found
            lines = text.splitlines()
            inserted = lines[:end] + [""] + fragment.rstrip("\n").splitlines() + lines[end:]
            return _preserve_trailing_newline(text, "\n".join(inserted))
    # No section anchor → append at EOF.
    suffix = "" if text.endswith("\n") else "\n"
    return text + suffix + "\n" + fragment


def _md_replace_section(text: str, section: str, fragment: str, card_name: str) -> str:
    found = _md_find_section(text, section)
    if not found:
        raise CardError(
            f"replace-section: section {section!r} not found in target "
            f"(card={card_name!r})"
        )
    start, end, _ = found
    lines = text.splitlines()
    # Quando a heading antiga é setext (title + underline) E o fragment substituto
    # usa ATX (`# Title`), o underline `===/---` ficaria órfão. `_md_find_section`
    # já garante que `end` é a próxima heading — então `lines[start:end]` cobre
    # todo o bloco (incluindo o underline em start+1 pra setext).
    replaced = lines[:start] + fragment.rstrip("\n").splitlines() + lines[end:]
    return _preserve_trailing_newline(text, "\n".join(replaced))


def _md_insert_relative(
    text: str, section: str, fragment: str, *, before: bool, card_name: str
) -> str:
    found = _md_find_section(text, section)
    if not found:
        raise CardError(
            f"{'before' if before else 'after'}-section: section {section!r} "
            f"not found in target (card={card_name!r})"
        )
    start, end, _ = found
    pivot = start if before else end
    lines = text.splitlines()
    inserted = lines[:pivot] + fragment.rstrip("\n").splitlines() + [""] + lines[pivot:]
    return _preserve_trailing_newline(text, "\n".join(inserted))
