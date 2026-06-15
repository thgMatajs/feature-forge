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
from pathlib import Path
from typing import Callable, Optional

from engine.ui.exit_codes import EXIT_CANCELLED, EXIT_PAUSED
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


# Subcommands que NÃO disparam bootstrap-state check — read-only/meta
# que precisam funcionar antes do `bash .claude/bootstrap.sh` ter rodado
# (ex.: usuário inspecionando versão ou pedindo ajuda pra descobrir como
# inicializar).
_BOOTSTRAP_SKIP_COMMANDS: frozenset[str] = frozenset({
    "--version",
    "-v",
    "--help",
    "-h",
    "help",
    "doctor",
    "bootstrap",  # reservado caso vire subcommand explícito no futuro
})


def _check_bootstrap_state(project_root: Path) -> Optional[str]:
    """Detect if bootstrap was run. Returns error message if missing, None if OK.

    Check: ``.git/hooks/pre-commit`` symlink existe (criado por
    ``.claude/bootstrap.sh``).

    Task 9.5 (graph-ia-evolution AC-11): friendly error pra novos devs
    que clonam o repo e tentam rodar comandos antes do bootstrap. NÃO
    auto-fixar (instalar symlinks silenciosamente é invasivo).

    Skip se:
    - ``.claude/`` não existe — não é projeto forge ainda (ou é bare
      repo de testes); deixar o handler dar a mensagem canônica.
    - ``hooks/git-pre-commit`` (no repo source) não existe — não é o
      repo da feature-forge em si; check de bootstrap só faz sentido
      pra mantenedores do próprio forge. Consumer projects que usam
      ``forge init`` recebem hooks por outra via.
    - ``.git`` é arquivo (git worktree linked) — hooks vivem no main
      repo, fora do path do worktree. Worktrees herdam o bootstrap
      do parent, então não é gap de UX local.
    """
    if not (project_root / ".claude").is_dir():
        return None
    if not (project_root / "hooks" / "git-pre-commit").is_file():
        return None
    if (project_root / ".git").is_file():
        # Linked worktree — hooks compartilhados com main repo.
        return None

    hooks_target = project_root / ".git" / "hooks" / "pre-commit"
    # Symlink válido (aponta pra target real) OU arquivo regular copiado
    # contam como state OK. Symlink quebrado (aponta pra path inexistente)
    # cai pra mensagem canônica — `is_symlink() and exists()` filtra esse
    # caso porque `exists()` resolve o link e retorna False em broken.
    is_valid = (hooks_target.is_symlink() and hooks_target.exists()) or hooks_target.is_file()
    if is_valid:
        return None
    return (
        "Atenção: forge não foi inicializado nesta máquina.\n"
        "   Rode: bash .claude/bootstrap.sh\n"
        "   (necessário uma vez após clone; idempotente)"
    )


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

    # Task 9.5 (graph-ia-evolution AC-11) — bootstrap-state check antes do
    # handler dispatch. Skip-list cobre comandos read-only/meta que
    # precisam rodar pré-bootstrap. Demais subcommands recebem friendly
    # error com instrução pra rodar `bash .claude/bootstrap.sh`.
    if cmd not in _BOOTSTRAP_SKIP_COMMANDS:
        try:
            from engine.utils.paths import find_project_root
            err = _check_bootstrap_state(find_project_root())
        except Exception:  # noqa: BLE001
            # Sem project root resolvível → não bloqueia; o handler dará a
            # mensagem canônica de ProjectRootNotFoundError.
            err = None
        if err:
            sys.stderr.write(err + "\n")
            return 1

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

    # Track the terminating exception so the ``finally`` block can decide
    # whether to wipe the consumed-intent log. Only ``PausedForInputError``
    # (exit 2, engine asked the caller for input) preserves the log so the
    # next re-invocation can skip already-answered intents (W7-fix re-entry
    # idempotency). Every other terminal path — success, user-cancel,
    # user-paused, fatal error — wipes it.
    paused_exc: PausedForInputError | None = None
    try:
        try:
            result = handler(rest)
        except PausedForInputError as exc:
            # DRIFT-1 §8 — chokepoint emitted .claude/state/forge-pending.json.
            # The caller (Claude Code host or engine.ui.tty_bridge) is expected
            # to read that file, write a response, and re-invoke us with the
            # same argv. No traceback, no message on stdout — the host renders
            # whatever it needs to from the intent payload itself.
            paused_exc = exc
            return EXIT_PAUSED
        except UserPausedError:
            # CR-003 fix — host response carried ``paused: true`` while the
            # prompt allowed pause. Same exit code as ``PausedForInputError``
            # (2 = clean pause, resumable) but a distinct semantic: the user
            # explicitly paused via response, rather than the engine emitting
            # a fresh pending. State already cleared by ``_check_pause_response``.
            #
            # Lifecycle note: even though this is exit 2, the user pause is a
            # *terminal* decision for THIS invocation — the engine is not
            # waiting for a follow-up response. Subsequent invocations start
            # fresh, so the log goes too.
            return EXIT_PAUSED
        except UserCancelledError:
            # CR-001 fix — host response carried ``cancelled: true``. Exit 130
            # parallels Ctrl+C (Decision 27 / SPEC §8). Placed before the
            # ``KeyboardInterrupt`` clause for readability; the types are
            # disjoint so ordering between these two does not matter
            # behaviourally.
            return EXIT_CANCELLED
        except KeyboardInterrupt:
            # Decision 27 / discipline §7 — Ctrl+C = pause.
            # Each command is responsible for serializing deferred state before
            # this point. We just report cleanly and exit 130 (POSIX SIGINT).
            sys.stderr.write("\n— interrompido, estado salvo.\n")
            return EXIT_CANCELLED
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
        # W7-fix lifecycle clear: at every terminal exit (success exit 0,
        # user-cancel exit 130, fatal error exit 1, user-paused exit 2)
        # wipe the consumed-intent log so the next forge invocation
        # starts with a clean slate. The exit-2 *engine-paused* branch
        # (``PausedForInputError``) opts out — detected via the
        # ``paused_exc`` sentinel captured by the except clause — because
        # the next re-invocation needs the log to skip already-answered
        # intents — that is the whole point of the idempotency mechanism.
        #
        # Critical: we use ``clear_intent_log_only`` here — NOT the full
        # ``clear_intent_files`` — because SPEC §3 mandates forensic
        # preservation of ``forge-pending.json`` and ``forge-response.json``
        # on error paths (mismatch, race, schema). The log is per-
        # invocation cache and safe to wipe; pending/response carry the
        # forensic evidence the user needs to debug.
        #
        # Failure to clear is silent: the delete is best-effort and any
        # IO error here is less harmful than the original engine failure
        # that we are trying to surface cleanly.
        if paused_exc is None:
            try:
                from engine.utils.paths import find_project_root

                project_root = find_project_root()
                intent_state.clear_intent_log_only(project_root)
            except Exception as exc:  # noqa: BLE001
                # Best-effort. If we cannot resolve project root or the
                # delete fails, do not mask the real exit code — but do
                # surface the failure so it shows up in logs / transcripts.
                # The original handler exit code is preserved by ``return``
                # already having executed before this ``finally`` block.
                sys.stderr.write(
                    f"[WARN] forge: failed to clear intent log on exit: {exc}\n"
                )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
