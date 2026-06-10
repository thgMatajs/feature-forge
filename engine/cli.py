"""CLI dispatcher — entry point for the `forge` Bash dispatcher.

Maps the 12 canonical subcommands (Decision 9) plus the hidden `ingest`
entry (used by hooks) to handlers in their respective modules.

No flags allowed (Decision 10) — argparse is intentionally **not** used.
We do a positional dispatch by `sys.argv[1]` only. Each subcommand
collects its own parameters via interactive prompts inside its handler.

Ctrl+C is treated as **pause**, never abort (Decision 27 / discipline §7):
the subcommand handler is responsible for saving deferred state before the
exception bubbles back here, where we exit with 130 (standard SIGINT code).

DRIFT-1 W2.T2 adds the **paused-for-input** clause. When a handler calls
``engine.ui.question.ask*`` and no response is on disk, the chokepoint
writes ``.claude/state/forge-pending.json`` and raises
``PausedForInputError`` — we catch it here and exit with code 2, the new
contract-bearer that says "intent emitted, caller please respond and
re-invoke" (SPEC §8).
"""

from __future__ import annotations

import importlib
import sys
from typing import Callable

from engine.ui.question import PausedForInputError

# Lazy imports — each command module is loaded only on first use, keeping
# cold-start fast for read-only commands like `forge status`.
COMMANDS: dict[str, tuple[str, str]] = {
    "init":        ("engine.init",        "run"),
    "plan":        ("engine.plan",        "run"),
    "implement":   ("engine.implement",   "run"),
    "verify":      ("engine.verify",      "run"),
    "status":      ("engine.status",      "run"),
    "doctor":      ("engine.doctor",      "run"),
    "reconfigure": ("engine.reconfigure", "run"),
    "graph":       ("engine.graph_cli",   "run"),
    "memory":      ("engine.memory_cli",  "run"),
    "evolve":      ("engine.evolve",      "run"),
    "undo":        ("engine.undo",        "run"),
    "raw":         ("engine.raw",         "run"),
    "qa":          ("engine.cli",         "_qa_run"),
    # Hidden — never advertised in --help, only invoked by hooks.
    # See docs/design/06-command-surface.md §Hidden internal entrypoints.
    "ingest":      ("engine.ingest",      "run"),
}

_VISIBLE_ORDER = (
    "init", "plan", "implement", "verify",
    "status", "doctor", "reconfigure", "graph",
    "memory", "evolve", "undo", "raw", "qa",
)


def _qa_run(argv: list[str]) -> int:
    """Wrapper that adapts the CLI dispatcher contract (``handler(argv)``)
    to ``engine.qa.run_qa``'s richer signature.

    The public ``run_qa`` API takes ``raw_target`` positional plus keyword-
    only ``project_root`` / ``workflow_config`` — deliberately decoupled
    from CLI argv parsing so it can be invoked by hooks or tests without
    going through ``sys.argv``. This wrapper resolves the project root and
    workflow-config inline, mirroring the pattern used by ``engine.verify``.

    ``raw_target`` comes from ``argv[0]`` if present; an empty argv is
    forwarded as ``""`` so ``resolve_scope`` can raise
    ``ScopeMissingError`` with its own mentor-calmo remediation block.

    Decision 10: no flags. The handler accepts only a positional target
    token. Anything beyond ``argv[0]`` is ignored at this layer (matches
    other handlers' tolerance for trailing hook-injected hints).
    """
    from engine.qa import run_qa
    from engine.utils.paths import (
        ProjectRootNotFoundError,
        find_project_root,
        workflow_config_path,
    )
    from engine.utils.yaml_io import read_yaml_or_default

    try:
        project_root = find_project_root()
    except ProjectRootNotFoundError as exc:
        sys.stderr.write(f"{exc}\n")
        return 1

    workflow_config = (
        read_yaml_or_default(workflow_config_path(project_root), {}) or {}
    )
    raw_target = argv[0] if argv else ""
    return run_qa(
        raw_target,
        project_root=project_root,
        workflow_config=workflow_config,
    )


def _resolve(cmd: str) -> Callable[[list[str]], int | None]:
    """Import the handler module on demand. Raises SystemExit on unknown cmd."""
    if cmd not in COMMANDS:
        raise SystemExit(
            f"forge: unknown subcommand '{cmd}'. Run 'forge' for help."
        )
    mod_path, fn_name = COMMANDS[cmd]
    try:
        mod = importlib.import_module(mod_path)
    except ModuleNotFoundError as exc:
        # Foundation wave ships before command modules — give a clear hint.
        raise SystemExit(
            f"forge: handler for '{cmd}' is not implemented yet "
            f"(missing module: {mod_path}). Details: {exc}"
        ) from exc
    handler = getattr(mod, fn_name, None)
    if handler is None:
        raise SystemExit(
            f"forge: module '{mod_path}' has no '{fn_name}' entry point."
        )
    return handler


def _print_help() -> None:
    """Render the top-level help. No flags listed — by design."""
    from engine import __version__

    lines: list[str] = []
    lines.append(f"forge {__version__} — feature-forge")
    lines.append("")
    lines.append("Usage: forge <subcomando>")
    lines.append("")
    lines.append("Subcomandos (13):")
    for cmd in _VISIBLE_ORDER:
        lines.append(f"  forge {cmd}")
    lines.append("")
    lines.append("Sem flags — todos os parâmetros são interativos (decisão 10).")
    lines.append("")
    lines.append("Mais: ~/Documents/feature-forge/docs/design/06-command-surface.md")
    sys.stdout.write("\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> int:
    """Top-level entry point. Returns a process exit code."""
    argv = list(sys.argv[1:] if argv is None else argv)

    if not argv:
        _print_help()
        return 0

    cmd, rest = argv[0], argv[1:]

    if cmd in ("-h", "--help", "help"):
        _print_help()
        return 0
    if cmd in ("-v", "--version"):
        from engine import __version__
        sys.stdout.write(f"forge {__version__}\n")
        return 0

    handler = _resolve(cmd)
    try:
        result = handler(rest)
    except PausedForInputError:
        # DRIFT-1 §8 — chokepoint emitted .claude/state/forge-pending.json.
        # The caller (Claude Code host or engine.ui.tty_bridge) is expected
        # to read that file, write a response, and re-invoke us with the
        # same argv. No traceback, no message on stdout — the host renders
        # whatever it needs to from the intent payload itself.
        return 2
    except KeyboardInterrupt:
        # Decision 27 / discipline §7 — Ctrl+C = pause.
        # Each command is responsible for serializing deferred state before
        # this point. We just report cleanly and exit 130 (POSIX SIGINT).
        sys.stderr.write("\n— interrompido, estado salvo.\n")
        return 130
    return int(result) if isinstance(result, int) else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
