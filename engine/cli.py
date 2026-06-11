"""CLI dispatcher — entry point for the `forge` Bash dispatcher.

Maps the 12 canonical subcommands (Decision 9) plus the hidden `ingest`
entry (used by hooks) to handlers in their respective modules.

No flags allowed (Decision 10) — argparse is intentionally **not** used.
We do a positional dispatch by `sys.argv[1]` only. Each subcommand
collects its own parameters via interactive prompts inside its handler.

Ctrl+C is treated as **pause**, never abort (Decision 27 / discipline §7):
the subcommand handler is responsible for saving deferred state before the
exception bubbles back here, where we exit with 130 (standard SIGINT code).

DRIFT-1 W2.T2 (+ W2 review remediation) wires the exit-code ladder:

- ``PausedForInputError``: engine emitted a fresh pending and is waiting
  on a first response → exit 2.
- ``UserPausedError``: host response carried ``"paused": true`` while
  ``allow_pause=True`` → exit 2 (also a clean pause, distinct semantic
  origin; CR-003 fix from W2 review).
- ``UserCancelledError``: host response carried ``"cancelled": true`` →
  exit 130, parallel to ``KeyboardInterrupt`` (CR-001 fix from W2 review).
- ``KeyboardInterrupt``: Ctrl+C on a TTY → exit 130 (Decision 27).

The ``_cli_command_context`` contextvar in ``engine.ui.question`` is set
here BEFORE dispatching to the handler so the pending JSON's ``command``
/ ``command-args`` reflect the argv ``main`` actually received, not the
parent process's ``sys.argv`` (HI-002 fix from W2 review).

Refs:
- docs/superpowers/specs/drift-1-intent-protocol.md §4, §8
- .planning/drift-1-w2-review/REVIEW.md (CR-001, CR-003, HI-002)
"""

from __future__ import annotations

import importlib
import sys
from typing import Callable

from engine.ui.question import (
    PausedForInputError,
    UserCancelledError,
    UserPausedError,
    _cli_command_context,
)

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
    # Lazy imports — keeps cli.main decoupled from foundation modules
    # until a control-flow path actually needs them, and matches the
    # lazy-import pattern already used by `_resolve` for command modules.
    # PR #11 review finding #1: surface `RaceDetectedError`,
    # `IntentMismatchError` (de `engine.ui.intent_state`) e `JsonIOError`
    # (de `engine.utils.json_io`) como exit 1 com mensagem mentor-calmo,
    # em vez de deixar o traceback Python cru vazar.
    from engine.ui import intent_state
    from engine.utils import json_io
    # HI-002 fix: publish (command, command-args) on the contextvar so
    # ``engine.ui.question._command_context`` can return the argv this
    # call to ``main`` received, even when ``sys.argv`` belongs to a
    # different parent process (pytest, REPL, library wrapper). The
    # ``reset`` in the ``finally`` undoes the set so concurrent test
    # cases never leak context across each other.
    token = _cli_command_context.set((cmd, list(rest)))
    try:
        try:
            result = handler(rest)
        except PausedForInputError:
            # DRIFT-1 §8 — chokepoint emitted .claude/state/forge-pending.json.
            # The caller (Claude Code host or engine.ui.tty_bridge) is expected
            # to read that file, write a response, and re-invoke us with the
            # same argv. No traceback, no message on stdout — the host renders
            # whatever it needs to from the intent payload itself.
            return 2
        except UserPausedError:
            # CR-003 fix — host response carried ``paused: true`` while the
            # prompt allowed pause. Same exit code as ``PausedForInputError``
            # (2 = clean pause, resumable) but a distinct semantic: the user
            # explicitly paused via response, rather than the engine emitting
            # a fresh pending. State already cleared by ``_check_pause_response``.
            return 2
        except UserCancelledError:
            # CR-001 fix — host response carried ``cancelled: true``. Exit 130
            # parallels Ctrl+C (Decision 27 / SPEC §8). Placed before the
            # ``KeyboardInterrupt`` clause for readability; the types are
            # disjoint so ordering between these two does not matter
            # behaviourally.
            return 130
        except KeyboardInterrupt:
            # Decision 27 / discipline §7 — Ctrl+C = pause.
            # Each command is responsible for serializing deferred state before
            # this point. We just report cleanly and exit 130 (POSIX SIGINT).
            sys.stderr.write("\n— interrompido, estado salvo.\n")
            return 130
        except (
            intent_state.RaceDetectedError,
            intent_state.IntentMismatchError,
        ) as exc:
            # PR #11 review #1 — DRIFT-1 intent-protocol sentinels carregam
            # mensagem mentor-calmo em ``exc.args[0]``. Sem este catch a
            # mensagem nunca chega ao usuário; em vez disso vaza traceback
            # cru, contrariando SPEC §3/§8 ("emite mensagem clara e exita 1").
            sys.stderr.write(f"{exc}\n")
            return 1
        except json_io.JsonIOError as exc:
            # PR #11 review #1 — falha ao decodificar state files
            # (.claude/state/forge-pending.json ou forge-response.json) é
            # erro de I/O, não bug interno do engine. Reportar limpo e
            # sair 1 em vez de traceback.
            sys.stderr.write(f"forge: erro de I/O lendo state file: {exc}\n")
            return 1
        return int(result) if isinstance(result, int) else 0
    finally:
        _cli_command_context.reset(token)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
