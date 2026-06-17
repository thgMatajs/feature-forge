"""`forge raw` — escape hatch.

Power-user invocation of internal scripts. Documented per-script in
`docs/design/06-command-surface.md §raw scripts`. No cinematic UI here —
plain `print()` is OK so output composes with `grep`, `jq`, pagers.

Scripts shipped in v1:
- `migrator-N-to-M` — config schema migrations (stub, Phase 5)
- `verify-card`     — validate a card.yaml against CARD-001..018
- `edit-config`     — open $EDITOR on workflow-config.yaml
- `rebuild-templates` — re-merge card contributions into templates
- `forge-debug`     — dump env + resolved paths + active cards
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from engine.cards.loader import CardError, load_all_cards, validate_card_yaml
from engine.cards.merger import merge_contributions, render_merged_template
from engine.utils.paths import (
    active_config_path,
    cards_dir,
    forge_home,
    try_find_project_root,
)
from engine.utils.yaml_io import backup_file, read_yaml


def run(argv: list[str]) -> int:
    """Dispatch `forge raw <script> [args...]`."""
    if not argv:
        _print_help()
        return 0

    script, rest = argv[0], argv[1:]
    handler = _SCRIPTS.get(script)
    if handler is None:
        if script.startswith("migrator-") and "-to-" in script:
            return _migrator(script, rest)
        print(f"forge raw: unknown script '{script}'", file=sys.stderr)
        _print_help()
        return 2
    return handler(rest)


def _print_help() -> None:
    print("forge raw — escape hatch for internal scripts")
    print()
    print("Available:")
    for name, desc in _SCRIPT_DESCRIPTIONS.items():
        print(f"  forge raw {name:<22} {desc}")
    print("  forge raw migrator-N-to-M   config schema migration N → M")


# ── verify-card ──────────────────────────────────────────────────────────────


def _verify_card(argv: list[str]) -> int:
    if not argv:
        print("usage: forge raw verify-card <card-dir>", file=sys.stderr)
        return 2
    card_dir = Path(argv[0]).resolve()
    if not card_dir.is_dir():
        print(f"forge raw verify-card: not a directory: {card_dir}", file=sys.stderr)
        return 2
    yaml_path = card_dir / "card.yaml"
    if not yaml_path.is_file():
        print(f"forge raw verify-card: card.yaml not found in {card_dir}", file=sys.stderr)
        return 2
    try:
        data = read_yaml(yaml_path)
    except Exception as exc:
        print(f"yaml parse error: {exc}", file=sys.stderr)
        return 1
    if not isinstance(data, dict):
        print("card.yaml: top-level must be a mapping", file=sys.stderr)
        return 1
    violations = validate_card_yaml(data, card_dir)
    if not violations:
        print(f"OK: {card_dir.name} valid")
        return 0
    print(f"FAIL: {card_dir.name} ({len(violations)} violation(s))")
    for v in violations:
        print(f"  · {v}")
    return 1


# ── edit-config ──────────────────────────────────────────────────────────────


def _edit_config(argv: list[str]) -> int:
    del argv
    project_root = try_find_project_root()
    if project_root is None:
        print("forge raw edit-config: no project root", file=sys.stderr)
        return 2
    path = active_config_path(project_root)
    if not path.is_file():
        print(f"forge raw edit-config: not found {path}", file=sys.stderr)
        return 2
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL") or "vi"
    print(f"opening {path} in {editor}")
    try:
        result = subprocess.run([editor, str(path)], check=False)
    except FileNotFoundError:
        print(f"editor '{editor}' not found on PATH", file=sys.stderr)
        return 127
    return result.returncode


# ── rebuild-templates ────────────────────────────────────────────────────────


def _rebuild_templates(argv: list[str]) -> int:
    """Re-merge card contributions into canonical templates.

    Loads every active card snapshot from `.claude/cards/`, runs
    `merge_contributions`, and for every distinct `target` writes the
    merged content back to `FORGE_HOME/templates/{target}`. Each target
    is backed up to `*.bak` before being overwritten.

    Returns 0 on success (with a report on stdout), 1 if at least one
    target fails to render, 2 when there is no project / no cards.
    """
    del argv
    project_root = try_find_project_root()
    if project_root is None:
        print("forge raw rebuild-templates: no project root", file=sys.stderr)
        return 2
    cards_root = cards_dir(project_root)
    if not cards_root.is_dir():
        print("no cards snapshot directory — run `forge init` first", file=sys.stderr)
        return 2

    print(f"scanning {cards_root}")
    try:
        cards = load_all_cards(cards_root)
    except CardError as exc:
        print(f"  ! load_all_cards failed: {exc}", file=sys.stderr)
        return 1
    if not cards:
        print("  no active cards — nothing to rebuild")
        return 0

    merged = merge_contributions(cards)
    if merged.warnings:
        for w in merged.warnings[:5]:
            print(f"  warn: {w}", file=sys.stderr)

    templates_root = forge_home() / "templates"
    if not templates_root.is_dir():
        print(f"  ! templates dir not found: {templates_root}", file=sys.stderr)
        return 1

    re_rendered = 0
    failures: list[str] = []
    for target, contributions in sorted(merged.templates.items()):
        target_path = templates_root / target
        if not target_path.is_file():
            failures.append(f"target not found: {target}")
            print(f"  ! {target}: file missing in templates/", file=sys.stderr)
            continue
        try:
            backup_file(target_path)
            render_merged_template(target_path, contributions, target_path)
            re_rendered += 1
            print(f"  ✓ {target} ({len(contributions)} contrib(s))")
        except CardError as exc:
            failures.append(f"{target}: {exc}")
            print(f"  ! {target}: {exc}", file=sys.stderr)

    print(f"re-rendered: {re_rendered} template(s)")
    if failures:
        print(f"failures: {len(failures)}", file=sys.stderr)
        return 1
    return 0


# ── forge-debug ──────────────────────────────────────────────────────────────


def _forge_debug(argv: list[str]) -> int:
    del argv
    print("== env ==")
    for key in ("FORGE_HOME", "EDITOR", "VISUAL", "NO_COLOR", "FORGE_FORCE_COLOR"):
        print(f"  {key:<18} = {os.environ.get(key, '')}")
    print()
    print("== paths ==")
    print(f"  forge_home          = {forge_home()}")
    project_root = try_find_project_root()
    print(f"  project_root        = {project_root}")
    if project_root is not None:
        cfg = active_config_path(project_root)
        print(f"  active config       = {cfg} (exists={cfg.is_file()})")
        cards_root = cards_dir(project_root)
        print(f"  cards snapshot dir  = {cards_root} (exists={cards_root.is_dir()})")
        if cards_root.is_dir():
            names = sorted(
                p.name for p in cards_root.iterdir()
                if p.is_dir() and not p.name.startswith(".") and not p.name.endswith(".bak")
            )
            print(f"  cards count         = {len(names)}")
            for n in names:
                print(f"    - {n}")
    print()
    print("== python ==")
    print(f"  executable          = {sys.executable}")
    print(f"  version             = {sys.version.split()[0]}")
    return 0


# ── migrator ────────────────────────────────────────────────────────────────


def _migrator(name: str, argv: list[str]) -> int:
    """Stub for schema migrators. Real impls land in Phase 5."""
    del argv
    print(f"forge raw {name}: not implemented yet (stub — Phase 5)", file=sys.stderr)
    return 3


# ── Dispatch table ──────────────────────────────────────────────────────────


_SCRIPTS = {
    "verify-card":       _verify_card,
    "edit-config":       _edit_config,
    "rebuild-templates": _rebuild_templates,
    "forge-debug":       _forge_debug,
}

_SCRIPT_DESCRIPTIONS = {
    "verify-card":       "validate a card.yaml against CARD-001..018",
    "edit-config":       "open workflow-config.yaml in $EDITOR",
    "rebuild-templates": "re-merge card contributions into FORGE_HOME/templates/",
    "forge-debug":       "dump env + resolved paths + cards count",
}


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(run(sys.argv[1:]))
