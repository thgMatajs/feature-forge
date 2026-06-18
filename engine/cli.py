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
import json
import sys
from pathlib import Path
from typing import Callable, Optional

from engine.ui import output_mode
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
    "upgrade":     ("engine.upgrade",     "run"),
    # Hidden — never advertised in --help, only invoked by hooks.
    # See docs/design/06-command-surface.md §Hidden internal entrypoints.
    "ingest":      ("engine.ingest",      "run"),
}

_VISIBLE_ORDER = (
    "init", "plan", "implement", "verify",
    "status", "doctor", "reconfigure", "graph",
    "memory", "evolve", "undo", "raw", "qa", "upgrade",
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
        active_config_path,
        find_project_root,
    )
    from engine.utils.yaml_io import read_yaml_or_default

    # Guard de args: sem scope target, imprime 3-caminhos mentor-calmo e sai
    # sem erro. Feito ANTES do find_project_root para que o user veja a
    # mensagem orientativa mesmo em dir nao-inicializado. O ValueError que
    # resolve_scope levantaria quando raw_target=="") nao e ScopeError e
    # portanto nao era capturado pelo except em run_qa — causava traceback
    # (Bug U4). Aqui interceptamos o caso de uso correto antes que chegue
    # ao resolve_scope.
    if not argv:
        sys.stdout.write(
            "forge qa requer um scope target. Tres caminhos:\n"
            "  A) forge qa paranoid    — sweep cross-feature\n"
            "  B) forge qa <slug>      — escopo single-feature\n"
            "  C) forge qa --help      — ver doc completa\n"
        )
        return 0

    try:
        project_root = find_project_root()
    except ProjectRootNotFoundError as exc:
        sys.stderr.write(f"{exc}\n")
        return 1

    workflow_config = (
        read_yaml_or_default(active_config_path(project_root), {}) or {}
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
#
# C-004 (master review PR #16, thgMatajs inline): ``graph``, ``status``,
# ``memory`` e ``raw`` são read-only e devem completar pré-bootstrap. UX
# pra novo dev que clona o repo e roda ``forge status`` pra inspecionar
# estado — bloquear com "rode bash .claude/bootstrap.sh" antes de o user
# sequer entender o que o comando faz é hostil. ``raw`` é a pipe genérica
# de leitura — mesmo princípio. Comandos que MUTAM state (``init``,
# ``plan``, ``implement``, ``verify``, ``reconfigure``, ``evolve``,
# ``undo``, ``qa``, ``ingest``) ficam fora da skip-list e continuam
# disparando o check.
_BOOTSTRAP_SKIP_COMMANDS: frozenset[str] = frozenset({
    "--version",
    "-v",
    "--help",
    "-h",
    "help",
    "doctor",
    "bootstrap",  # reservado caso vire subcommand explícito no futuro
    "graph",      # read-only — query menu sobre graph.db
    "status",     # read-only — inspeção de estado
    "memory",     # read-only — leitura/listagem de L1/L2/L3
    "raw",        # read-only — pipe genérica de leitura
    "upgrade",    # opera no FORGE_HOME, não no projeto consumidor — sem project root
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
    from engine.utils.paths import forge_home

    lines: list[str] = []
    lines.append(f"forge {__version__} — feature-forge")
    lines.append("")
    lines.append("Usage: forge <subcomando>")
    lines.append("")
    lines.append("Subcomandos (14):")
    for cmd in _VISIBLE_ORDER:
        lines.append(f"  forge {cmd}")
    lines.append("")
    lines.append("Sem flags — todos os parâmetros são interativos (decisão 10).")
    lines.append("")
    # M9 HELP-DOC-PATH (W-DEBT): resolver via forge_home() — respeita XDG
    # (~/.local/share/feature-forge) e qualquer FORGE_HOME custom, em vez do
    # ~/Documents/... hardcoded que não resolvia em instalações XDG.
    doc_path = forge_home() / "docs" / "design" / "06-command-surface.md"
    lines.append(f"Mais: {doc_path}")
    sys.stdout.write("\n".join(lines) + "\n")


# A2 NO-MANIFEST — static per-command metadata for the machine manifest.
# Hand-maintained in lockstep with `_VISIBLE_ORDER`/`COMMANDS` (NOT auto-derived
# from them) — `_print_help_json` iterates `_VISIBLE_ORDER` and looks each name
# up here. The drift guard `test_command_meta_keys_match_visible_order` fails if
# a command is added without a metadata entry (W-001). Read-commands advertise
# --json (Decisão 10 revisitada — meta-flags carve-out). Voz mentor-calmo nos summaries.
_COMMAND_META: dict[str, dict] = {
    "init":        {"summary": "Inicializa forge no projeto (mapa cinemático).", "interactive": True,  "flags": [],         "args": []},
    "plan":        {"summary": "Planeja uma feature (conversacional).",          "interactive": True,  "flags": [],         "args": ["feature-slug?"]},
    "implement":   {"summary": "Implementa a feature planejada.",                "interactive": True,  "flags": [],         "args": ["feature-slug?"]},
    "verify":      {"summary": "Roda o cascade de validators (read-only).",      "interactive": False, "flags": ["--json"], "args": ["task TASK-NNNN | feature SLUG?"]},
    "status":      {"summary": "Board read-only do projeto.",                    "interactive": False, "flags": ["--json"], "args": []},
    "doctor":      {"summary": "Health check read-only.",                        "interactive": False, "flags": ["--json"], "args": []},
    "reconfigure": {"summary": "Atualiza config com diff incremental.",          "interactive": True,  "flags": [],         "args": []},
    "graph":       {"summary": "Consulta o codebase graph.",                     "interactive": False, "flags": ["--json"], "args": ["query args"]},
    "memory":      {"summary": "Inspeciona/gerencia memory layers.",             "interactive": False, "flags": ["--json"], "args": []},
    "evolve":      {"summary": "Review-and-apply de proposed evolutions.",       "interactive": True,  "flags": [],         "args": []},
    "undo":        {"summary": "Reverte mutações (2-step abort).",               "interactive": True,  "flags": [],         "args": []},
    "raw":         {"summary": "Passthrough cru.",                               "interactive": True,  "flags": [],         "args": ["args"]},
    "qa":          {"summary": "QA red-team (auditores hostis).",                "interactive": True,  "flags": [],         "args": ["target?"]},
    "upgrade":     {"summary": "Atualiza snapshot da forge.",                    "interactive": True,  "flags": [],         "args": []},
}


def _print_help_json() -> None:
    """Emit the machine-readable command manifest (A2 NO-MANIFEST).

    Only visible commands (``_VISIBLE_ORDER``) are listed — the hidden
    ``ingest`` entrypoint is intentionally omitted, mirroring the prose help.
    stdout is pure JSON (graph model); a consumer parses this instead of
    inferring the surface from prose (the failure mode that made the audit's
    second LLM hallucinate ~75% of its findings).
    """
    from engine import __version__

    commands = []
    for name in _VISIBLE_ORDER:
        meta = _COMMAND_META.get(name, {})
        commands.append(
            {
                "name": name,
                "summary": meta.get("summary", ""),
                "interactive": meta.get("interactive", True),
                "hidden": False,
                "flags": list(meta.get("flags", [])),
                "args": list(meta.get("args", [])),
            }
        )
    manifest = {"forge_version": __version__, "commands": commands}
    print(json.dumps(manifest, indent=2, default=str))


def main(argv: list[str] | None = None) -> int:
    """Top-level entry point. Returns a process exit code."""
    argv = list(sys.argv[1:] if argv is None else argv)

    if not argv:
        _print_help()
        return 0

    cmd, rest = argv[0], argv[1:]

    # A1 TOKEN-BLIND — resolve the process output-mode ONCE at startup and
    # publish it on the context var so renderer.write (the single chokepoint)
    # and read-command handlers consult a single source of truth. ``command=cmd``
    # GATES JSON resolution to the read-command allowlist (Decisão de design 2):
    # an interactive command never resolves JSON even under FORGE_OUTPUT=json,
    # so its cinematic UX + intent protocol are never silently degraded. The
    # reset lives in the outermost ``finally`` below, mirroring the set/reset
    # discipline of ``_cli_command_context``.
    _output_mode_token = output_mode.set_output_mode(
        output_mode.detect_output_mode(argv, command=cmd)
    )
    try:
        return _main_dispatch(cmd, rest, argv)
    finally:
        output_mode.reset_output_mode(_output_mode_token)


def _main_dispatch(cmd: str, rest: list[str], argv: list[str]) -> int:
    """Resolve + dispatch a subcommand. Output-mode is already set by ``main``."""
    if cmd in ("-h", "--help", "help"):
        # A2 NO-MANIFEST — ``forge --help --json`` emits the machine manifest.
        # It does NOT depend on the resolved output-mode (``--help`` is not in
        # the read-command allowlist), so we detect ``--json`` positionally.
        if "--json" in rest or "--json" in argv:
            _print_help_json()
        else:
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
        from engine.utils.paths import (
            ProjectRootNotFoundError,
            find_project_root,
        )
        try:
            err = _check_bootstrap_state(find_project_root())
        except ProjectRootNotFoundError:
            # Sem project root resolvível → não bloqueia; o handler dará a
            # mensagem canônica de ProjectRootNotFoundError.
            #
            # M-014 fix (master review PR #16): except narrow em vez de
            # ``except Exception``. Outras exceptions (OSError, perms,
            # bugs) propagam — telemetria preservada. O handler ainda
            # roda e dá mensagem canônica pro caso esperado.
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

    # Bug U2 — suppress intent-log cleanup WARN for help/no-args paths.
    # These paths return before reaching the try…finally, but we record the
    # sentinel here so that if the control flow ever changes the finally
    # stays silent. The check mirrors the early-return conditions above.
    is_help_path = not argv or argv[0] in ("-h", "--help", "help", "-v", "--version")

    # Track the terminating path so the ``finally`` block can pick the
    # right cleanup contract (BL-001 fix). Three buckets:
    #
    # - ``paused_exc`` set → engine-paused (exit 2, ``PausedForInputError``):
    #   preserve EVERYTHING (pending+response+log). The next re-invocation
    #   needs the pending it just emitted plus the log to skip already-
    #   answered intents (W7-fix re-entry idempotency).
    # - ``forensic_exit`` set → intent-protocol error (exit 1: mismatch /
    #   race / schema / JSON I/O): wipe only the log, PRESERVE
    #   pending+response so the user can inspect them (SPEC §3 forensic rule).
    # - neither set → success (exit 0), user-cancel (exit 130) or
    #   user-paused-via-response (exit 2 ``UserPausedError``): these are
    #   TERMINAL decisions for this lifecycle with nothing to preserve, so
    #   wipe pending+response+log and the NEXT command starts on a clean
    #   slate. Leaving pending/response behind on success is exactly what
    #   made a subsequent command with a different intent-id raise
    #   ``IntentMismatchError`` / ``RaceDetectedError`` (BL-001).
    paused_exc: PausedForInputError | None = None
    forensic_exit = False
    try:
        # C3 EXIT-2-COLLISION — exit 2 é reservado ESTRITAMENTE pra pausa
        # (PausedForInputError + UserPausedError). Todos os erros dos handlers
        # colapsaram em exit 1 + tag [FORGE-ERR:<TAG>] (ver engine/ui/exit_codes.py
        # fail_with_tag). Nenhuma exceção não-pausa pode retornar 2 a partir
        # daqui.
        try:
            result = handler(rest)
        except PausedForInputError as exc:
            # DRIFT-1 §8 — chokepoint emitted .claude/forge/state/forge-pending.json.
            # The caller (Claude Code host or the in-process TtyAdapter) is expected
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
            # a fresh pending.
            #
            # Lifecycle note: even though this is exit 2, the user pause is a
            # *terminal* decision for THIS invocation — the engine is not
            # waiting for a follow-up response. Subsequent invocations start
            # fresh, so the ``finally`` wipes pending+response+log (it is NOT
            # the engine-paused ``PausedForInputError`` branch).
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
            intent_state.SchemaVersionMismatchError,
        ) as exc:
            # PR #11 review #1 — DRIFT-1 intent-protocol sentinels carregam
            # mensagem mentor-calmo em ``exc.args[0]``. Sem este catch a
            # mensagem nunca chega ao usuário; em vez disso vaza traceback
            # cru, contrariando SPEC §3/§8 ("emite mensagem clara e exita 1").
            #
            # SCHEMA-LEAK (W-DEBT): SchemaVersionMismatchError (RuntimeError)
            # entra aqui pra version skew dar exit 1 mentor-calmo em vez de
            # traceback cru. É caminho forense (forensic_exit = True).
            #
            # BL-001: caminho de erro do intent-protocol — preserva
            # pending/response pra forense (SPEC §3); o ``finally`` limpa só
            # o log.
            forensic_exit = True
            sys.stderr.write(f"{exc}\n")
            return 1
        except json_io.JsonIOError as exc:
            # PR #11 review #1 — falha ao decodificar state files
            # (.claude/forge/state/forge-pending.json ou forge-response.json) é
            # erro de I/O, não bug interno do engine. Reportar limpo e
            # sair 1 em vez de traceback.
            #
            # BL-001: também é caminho de erro — preserva pending/response
            # pra forense; o ``finally`` limpa só o log.
            forensic_exit = True
            sys.stderr.write(f"forge: erro de I/O lendo state file: {exc}\n")
            return 1
        return int(result) if isinstance(result, int) else 0
    finally:
        _cli_command_context.reset(token)
        # BL-001 lifecycle clear — the cleanup contract now depends on HOW
        # this invocation terminated (see the ``paused_exc`` / ``forensic_exit``
        # comment where the trackers are declared):
        #
        # - engine-paused (``paused_exc`` set, ``PausedForInputError``,
        #   exit 2) → clear NOTHING. The next re-invocation needs the pending
        #   it just emitted plus the log to skip already-answered intents.
        # - intent-protocol error (``forensic_exit`` set, exit 1: mismatch /
        #   race / schema / JSON I/O) → ``clear_intent_log_only``: wipe the
        #   per-invocation log but PRESERVE pending/response, because SPEC §3
        #   mandates forensic preservation on error paths so the user can
        #   inspect the evidence.
        # - success / user-cancel / user-paused-via-response (exit 0/130/2,
        #   neither tracker set) → ``clear_intent_files(also_log=True)``: wipe
        #   pending+response+log. These are terminal decisions with nothing
        #   to preserve; leaving pending/response behind made the NEXT command
        #   (different intent-id) raise ``IntentMismatchError`` /
        #   ``RaceDetectedError`` (BL-001). Clearing on success closes that
        #   leak and finally honours the contract documented on
        #   ``clear_intent_log_only``.
        #
        # Help / no-args paths return before the try, so the ``finally`` runs
        # but ``is_help_path`` guards out — nothing to clean there.
        #
        # Failure to clear is silent: the delete is best-effort and any IO
        # error here is less harmful than the original handler outcome we are
        # trying to surface cleanly.
        if paused_exc is None and not is_help_path:
            try:
                from engine.utils.paths import (
                    ProjectRootNotFoundError,
                    find_project_root,
                )

                project_root = find_project_root()
                if forensic_exit:
                    intent_state.clear_intent_log_only(project_root)
                else:
                    intent_state.clear_intent_files(project_root, also_log=True)
            except ProjectRootNotFoundError:
                # Pre-init dir: nao ha project root resolvivel, logo nao ha
                # intent-log a limpar. Silencioso por design — o handler ja
                # emitiu a mensagem canonica de nao-inicializado; um WARN
                # adicional aqui seria ruido confuso (Bug U2 residual).
                pass
            except Exception as exc:  # noqa: BLE001
                # Best-effort. If we cannot resolve project root or the
                # delete fails, do not mask the real exit code — but do
                # surface the failure so it shows up in logs / transcripts.
                # The original handler exit code is preserved by ``return``
                # already having executed before this ``finally`` block.
                sys.stderr.write(
                    f"[WARN] forge: failed to clear intent state on exit: {exc}\n"
                )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
