"""Interactive prompts — the engine-side chokepoint of the DRIFT-1 intent protocol.

Originally this module bridged subcommands to ``sys.stdin``. Post DRIFT-1
W2 (spec ``docs/superpowers/specs/drift-1-intent-protocol.md``) it does
the opposite: each ``ask*`` entrypoint either consumes a matching response
from ``.claude/state/forge-response.json`` (returning the value) or emits
a canonical pending intent to ``.claude/state/forge-pending.json`` and
raises ``PausedForInputError``. The top-level handler in ``engine.cli``
maps that sentinel to exit code 2.

In the TTY path stdin is read in-process by ``engine.host.adapters.tty``
(``TtyAdapter``); in the agentic path the engine emits intent files and the
host (Claude Code / opencode) writes responses to disk. No subcommand calls
stdin directly — this module is the single point of input.

Invariants honoured here (the refactor preserves them bit-a-bit):

- API surface — ``ask``, ``ask_text``, ``ask_multi``, ``confirm``,
  ``ask_three_paths`` keep their exact signatures. 108 callsites across
  10 engine modules continue to compile and run untouched. (The number
  comes from the canonical grep
  ``grep -rEn "question\\.(ask|ask_text|ask_multi|confirm|ask_three_paths)" engine/``
  — counts every unique attribute access. Earlier docs cited 106 / 125
  using slightly different criteria; 108 is the authoritative figure
  per the canonical grep methodology.)
- ``PromptAbortedError`` / ``NonInteractiveError`` still ship from this
  module (callers ``except`` them). DRIFT-1 W2 review reclassified the
  user-action channels into dedicated sentinels — ``UserCancelledError``
  for ``cancelled: true`` (maps to exit 130) and ``UserPausedError`` for
  ``paused: true`` with ``allow_pause=True`` (maps to exit 2). The
  legacy classes stay exported for backward compatibility with the 10
  callsite modules.
- ``_PAUSE_TOKENS`` (``para``, ``pausa``, ``quit``, ``q``, ``exit``) keep
  their values — the tokens are recognised on the response side now,
  not on stdin.
- ``allow_pause=False`` semantics preserved: a paused response raises
  ``ValueError`` (pause forbidden in this context).
- Forensic state preservation (SPEC §3): invalid schema/value branches
  raise ``ValueError`` WITHOUT clearing ``.claude/state/*`` — the files
  remain on disk so the host can inspect what arrived. Only success
  paths and user-initiated termination (pause / cancel) clear state.

Refs:
- docs/superpowers/specs/drift-1-intent-protocol.md §2, §3, §4, §6, §8
- docs/schemas/intent-protocol.md
- docs/superpowers/plans/drift-1-intent-protocol.md W2.T1
- .planning/drift-1-w2-review/REVIEW.md (CR-001..LO-003)
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from engine.ui import intent_state
from engine.utils.paths import try_find_project_root


class PromptAbortedError(RuntimeError):
    """Legacy sentinel — kept exported for backward compatibility.

    Pre-DRIFT-1 this fired off a stdin read; in the original W2 wiring
    it also fired when the response carried ``"paused": true`` or
    ``"cancelled": true``. Post W2-review the user-action channels were
    split into ``UserPausedError`` and ``UserCancelledError`` so the
    ``cli.main`` ladder can map them to distinct exit codes (2 and 130
    respectively). ``PromptAbortedError`` itself is no longer raised by
    the chokepoint — it remains in the module surface because the 10
    callsite modules still write ``except PromptAbortedError:`` clauses
    we are forbidden from touching in this scope. New code should use
    ``UserPausedError`` / ``UserCancelledError``.
    """


class NonInteractiveError(RuntimeError):
    """Raised when a prompt fires without a response and pause is forbidden.

    Kept for API stability — callers may still ``except NonInteractiveError``.
    DRIFT-1 superseded the stdin-EOF path that used to raise it; the
    sentinel is now reached via ``allow_pause=False`` + ``paused: true``
    on the response, which the host adapter resolves to a ``ValueError``
    (pause forbidden in this context) — see the pause/cancel handling in
    ``engine/host/adapter.py``.
    """


class PausedForInputError(Exception):
    """Sentinel raised by the chokepoint when no response is available yet.

    ``intent`` carries the dict that was just written to
    ``.claude/state/forge-pending.json`` — the host (Claude Code,
    opencode, or ``TtyAdapter`` in the TTY path) reads that file and
    writes a response;
    the engine is then re-invoked with the same argv and consumes the
    response on its way back through this module.

    ``engine.cli::main()`` catches this sentinel and returns exit code 2
    (SPEC §8). It is NOT a ``RuntimeError`` so callers that ``except
    RuntimeError`` (the legacy abort path) do not accidentally swallow
    it — this is control flow, not failure.

    Distinct from ``UserPausedError``: ``PausedForInputError`` fires
    when the engine emits a fresh pending and there is no response yet;
    ``UserPausedError`` fires when the host wrote ``paused: true`` in
    the response. Both map to exit 2 but the semantics differ — the
    first means "need input", the second means "user explicitly paused".
    """

    intent: dict[str, Any]

    def __init__(self, *, intent: dict[str, Any]) -> None:
        super().__init__(f"forge paused awaiting input (intent-id={intent.get('intent-id')!r})")
        self.intent = intent


class UserCancelledError(Exception):
    """Sentinel raised when the host response carries ``"cancelled": true``.

    Distinct from ``KeyboardInterrupt`` (Ctrl+C on a TTY) but maps to the
    same exit code — 130 — per SPEC §8. Caught by ``engine.cli::main()``
    BEFORE the ``KeyboardInterrupt`` clause; both clean up state and
    terminate the process with the canonical SIGINT exit code.

    Sibling of ``PausedForInputError`` (not a ``RuntimeError``) so legacy
    ``except RuntimeError`` ladders cannot accidentally swallow user
    cancellation as a generic failure.
    """


class UserPausedError(Exception):
    """Sentinel raised when the host response carries ``"paused": true``
    AND ``allow_pause=True`` on the originating prompt.

    Maps to exit code 2 per SPEC §8 — same as ``PausedForInputError``
    but with a different semantic origin (user explicitly paused via
    response, rather than engine emitting a fresh pending). Caught by
    ``engine.cli::main()`` and translated cleanly without a traceback.

    Sibling of ``PausedForInputError`` (not a ``RuntimeError``) so legacy
    ``except RuntimeError`` ladders cannot swallow it.
    """


_PAUSE_TOKENS = {"para", "pausa", "quit", "q", "exit"}

_SCHEMA_VERSION = 1


# --- ContextVar for command-context (HI-002 fix) ---------------------------
#
# ``engine.cli.main(argv)`` accepts an explicit ``argv`` for programmatic
# invocation (tests, harnesses). When that argv differs from
# ``sys.argv`` — which happens whenever ``main`` is invoked from inside
# pytest, a REPL, or any library wrapper — the pending JSON's
# ``command`` / ``command-args`` fields must reflect the argv ``main``
# actually received, not the parent process's argv.
#
# ``cli.main`` sets this contextvar BEFORE dispatching to the handler;
# ``_command_context()`` reads it. Production calls via
# ``bin/forge`` → ``python -m engine.cli ...`` keep ``sys.argv``
# consistent with ``main(argv=None)``, so the fallback to ``sys.argv``
# below is the legitimate hot path; the contextvar simply makes
# programmatic invocation faithful too.

_cli_command_context: ContextVar[tuple[str, list[str]] | None] = ContextVar(
    "_cli_command_context", default=None
)


# stdin is read in-process by TtyAdapter (engine/host/adapters/tty.py) on the
# TTY path; this module never reads stdin directly.


# --- Intent-id derivation --------------------------------------------------


def stable_intent_id(
    kind: str,
    question_text: str,
    options: Mapping[str, str] | None,
    extra: Mapping[str, Any] | None = None,
    *,
    command: str | None = None,
    command_args: Sequence[str] | None = None,
) -> str:
    """Deterministic intent-id for o (kind, question, options, call-site) tuple.

    **Public API** (finding #8 do master review do PR #11): originalmente
    declarada com underscore prefix (``_stable_intent_id``) mas consumida
    por 13 callsites de produção em 10 módulos. O underscore mascarava o
    fato de ser API pública de facto. Renomeada para ``stable_intent_id``
    e adicionada à export surface explícita deste módulo. O alias
    deprecated ``_stable_intent_id`` permanece exportado para preservar
    callsites legados — será removido em v1.3.

    A stable id lets a re-invocation of the same command + same prompt
    line up with the response on disk without callers having to thread
    an explicit id through their signatures (which would break the
    invariant in the module docstring). The id is *not* a security
    token — it is a wire correlation key.

    O call-site (``command`` + ``command_args``) entra no payload do
    hash para resolver o finding #2 do master review do PR #11:
    sem isso, ``ask("Continue?")`` repetido em dois subcomandos
    distintos produzia o MESMO intent-id, fazendo uma response do
    primeiro ser indevidamente consumida pelo segundo. Quando os
    parâmetros vêm como ``None``, recorre-se a ``_command_context()``
    (mesma resolução contextvar → ``sys.argv`` usada por
    ``_build_pending``) para manter os 13 callsites legados em sync
    com o intent-id calculado pelo chokepoint, sem precisar mudar
    nenhum dos callsites no escopo desta wave.

    The shape is a UUID-formatted SHA-256 prefix: 8-4-4-4-12 hex chars,
    32 hex digits total. UUID format is what the spec § 2.1 example
    declares; using a hash instead of ``uuid.uuid4()`` makes the id
    reproducible across process restarts.
    """
    if command is None or command_args is None:
        ctx_cmd, ctx_args = _command_context()
        if command is None:
            command = ctx_cmd
        if command_args is None:
            command_args = ctx_args
    payload = json.dumps(
        {
            "kind": kind,
            "question": question_text,
            "options": dict(options) if options is not None else None,
            "extra": dict(extra) if extra is not None else None,
            "command": command,
            "command-args": list(command_args),
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
    return f"{digest[0:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:32]}"


# Backward-compat alias (deprecated) — preserva os 13 callsites legados
# em ``engine/{plan,implement,verify,reconfigure,evolve,undo,memory_cli,
# graph_cli,init,doctor}.py`` + 4 testes em ``tests/unit/``. Remover em
# v1.3 quando todos os callers forem migrados para ``stable_intent_id``.
_stable_intent_id = stable_intent_id


# --- Project root + state-file plumbing ------------------------------------


def _project_root_for_io() -> Path:
    """Resolve the project root used to anchor ``.claude/state/*``.

    Walks up from ``cwd`` looking for ``.claude/workflow-config.yaml``;
    falls back to ``cwd`` when no marker is found. The fallback keeps
    smoke tests (and one-off ``python -m engine.cli`` invocations from
    odd directories) operational — they will write into the current
    directory's ``.claude/state/``.
    """
    found = try_find_project_root()
    return found if found is not None else Path.cwd()


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _command_context() -> tuple[str, list[str]]:
    """Recovery of (command, command-args) — contextvar first, ``sys.argv`` fallback.

    Resolution order (HI-002 fix from W2 review):

    1. ``_cli_command_context`` contextvar — set by ``engine.cli.main``
       before dispatching to the handler. This is the faithful source
       whenever ``main`` was invoked with an explicit ``argv`` (tests,
       harnesses, library wrappers).
    2. ``sys.argv`` fallback — when the contextvar is unset (engine is
       being driven without going through ``cli.main``, e.g. a unit test
       calling ``question.ask`` directly). Production use through
       ``bin/forge`` lands here too because ``main`` always runs and
       sets the contextvar before dispatch; the contextvar set + the
       ``sys.argv`` shape are consistent in that path.
    3. ``("unknown", [])`` last-resort when even ``sys.argv`` is empty.

    The contextvar carries the same shape ``(command, command_args)`` so
    the rest of this module is agnostic to where the data came from.
    """
    captured = _cli_command_context.get()
    if captured is not None:
        return captured

    argv = sys.argv
    if not argv:
        return ("unknown", [])
    # ``python -m engine.cli init foo`` → argv == ["...cli.py", "init", "foo"]
    # ``forge init foo`` → bin/forge execs python -m engine.cli, same shape.
    head = Path(argv[0]).name
    if len(argv) >= 2:
        return (argv[1], list(argv[2:]))
    # MD-fix #12: normaliza fallback quando só argv[0] está disponível —
    # ``"cli.py"`` ou ``"__main__"`` não são nomes de comando válidos
    # e só poluem o JSON. Mapeia para a sentinela ``"unknown"``.
    if head == "__main__" or head.endswith(".py"):
        return ("unknown", [])
    return (head or "unknown", [])


def _build_pending(
    *,
    kind: str,
    question_text: str,
    options: Mapping[str, str] | None,
    default: str | None,
    allow_pause: bool,
    validator_hint: str | None = None,
    min_selected: int | None = None,
    paths_detail: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Assemble the canonical pending payload (matches docs/schemas/intent-protocol.md).

    The ``extra`` mapping fed into ``stable_intent_id`` includes
    ``validator-hint`` (MD-001 fix from W2 review): two ``ask_text``
    calls with the same prompt but different validators MUST produce
    distinct intent-ids, otherwise a stale response intended for
    validator A could be consumed by a call expecting validator B.
    The validator callable itself is not deterministically hashable;
    ``validator_hint`` is the public-facing proxy and is stable enough
    for wire correlation.
    """
    command, command_args = _command_context()
    extra_for_hash: dict[str, Any] = {
        "default": default,
        "min-selected": min_selected,
        "validator-hint": validator_hint,
    }
    # MD-fix #11: paths-detail entra no hash apenas quando presente,
    # para preservar parity bit-a-bit com os 13 callsites legados
    # (engine/{plan,implement,verify,...}.py) que pré-calculam o
    # intent-id sem essa chave. O rename + uniformização desses
    # callsites é Wave 2 (#8); até lá, omitir a chave por completo
    # quando paths-detail é ``None`` mantém o resume intacto.
    if paths_detail is not None:
        extra_for_hash["paths-detail"] = [dict(item) for item in paths_detail]
    intent: dict[str, Any] = {
        "schema-version": _SCHEMA_VERSION,
        "intent-id": stable_intent_id(
            kind,
            question_text,
            options,
            extra=extra_for_hash,
            command=command,
            command_args=command_args,
        ),
        "command": command,
        "command-args": command_args,
        "kind": kind,
        "question": question_text,
        "options": dict(options) if options is not None else None,
        "default": default,
        "allow-pause": allow_pause,
        "created-at": _now_iso(),
        "pid": os.getpid(),
        "checkpoint-path": None,
    }
    if validator_hint is not None:
        intent["validator-hint"] = validator_hint
    if min_selected is not None:
        intent["min-selected"] = min_selected
    if paths_detail is not None:
        intent["paths-detail"] = paths_detail
    return intent


# NOTE (BL-001 / MD-001): a antiga geração de helpers nativos do
# chokepoint — ``_emit_pending_and_raise``, ``_consume_response_or_none``,
# ``_clear_state`` e ``_check_pause_response`` — foi removida quando
# ``ask``/``ask_multi``/``ask_text`` e, por fim, ``confirm``/
# ``ask_three_paths`` passaram a delegar pro ``HostAdapter`` (Task 0.7b +
# série de remediação PR #17). A semântica de pause/cancel/clear hoje vive
# no adapter (ver ``engine/host/adapter.py`` e o loop em
# ``IntentFileAdapter``); o cleanup terminal de pending/response/log é
# responsabilidade do ``finally`` de ``engine/cli.py::main`` (BL-001).
# Mantê-los aqui como código morto só desorientava o próximo leitor sobre
# quem limpa o quê.


# --- Adapter resolution (Task 0.7b) ----------------------------------------


def _resolve_adapter(project_root: Path):
    """Resolve the host adapter for this project; bootstraps the registry lazily.

    Task 0.7b — surgical delegate of ``ask``/``ask_multi``/``ask_text`` to
    the host-adapter ABC defined in ``engine.host.adapter``. The lazy
    bootstrap registers the native adapters on first call so production
    code does not need an explicit setup hook at import time. Wave 2
    registers ``TtyAdapter`` (caminho TTY humano in-process — substitui o
    antigo ``tty_bridge`` subprocess-loop).

    OPENCODE — Veredito B (docs/research/opencode-tool-api.md):
    opencode captura stdout do subprocess ao final da execucao; nao ha
    interceptacao de marker em tempo real nem canal subprocess→host para
    acionar a ``question`` tool. Portanto nao e compativel com o shape do
    ``ClaudeCodeAdapter``. O registro abaixo e explicito (nao mais um
    KeyError acidental): OPENCODE usa ``IntentFileAdapter`` como fallback
    documentado. O protocolo DRIFT-1 funciona em qualquer ambiente com
    acesso a disco, incluindo o bash-tool do opencode.
    """
    from engine.host.detect import detect_host
    from engine.host.registry import get_adapter_class, register
    from engine.host.adapter import HostName

    try:
        get_adapter_class(HostName.INTENT_FILE)
    except KeyError:
        from engine.host.adapters.intent_file import IntentFileAdapter
        from engine.host.adapters.claude_code import ClaudeCodeAdapter
        from engine.host.adapters.tty import TtyAdapter

        register(HostName.INTENT_FILE, IntentFileAdapter)
        register(HostName.CLAUDE_CODE, ClaudeCodeAdapter)
        register(HostName.TTY, TtyAdapter)
        # Veredito B: opencode nao suporta adapter in-process (ver docstring).
        # Registro explicito aqui documenta a decisao; sem isso, OPENCODE
        # cairia no KeyError abaixo por acidente, sem intencao registrada.
        register(HostName.OPENCODE, IntentFileAdapter)

    host = detect_host(project_root)
    try:
        cls = get_adapter_class(host)
    except KeyError:
        # Rede de seguranca para hosts genuinamente desconhecidos (nao OPENCODE —
        # esse ja esta registrado acima). IntentFileAdapter e o fallback mais
        # seguro: funciona em qualquer ambiente com acesso a disco.
        cls = get_adapter_class(HostName.INTENT_FILE)
    return cls(project_root=project_root)


def _read_adapter_pending_or_fallback(
    project_root: Path, fallback: dict[str, Any]
) -> dict[str, Any]:
    """Return the canonical pending dict the adapter just wrote to disk.

    Task 0.7b — when ``adapter.ask*`` raises ``PausedForInputError`` it
    has already written ``forge-pending.json`` to the resolved
    ``state_dir`` (``.claude/forge/state/`` for the IntentFileAdapter).
    Reading it back is the authoritative source of the intent-id and
    other wire fields, which guarantees that the ``intent`` payload
    surfaced via ``question.PausedForInputError.intent`` matches what
    callers will see on disk (e.g. tests that write a response keyed by
    ``exc.value.intent['intent-id']``). When the read fails — host did
    not write a pending file (TTY adapter in W2, transient I/O glitch)
    — fall back to the in-process intent dict so callers still get
    something coherent.
    """
    from engine.utils.paths import forge_state_dir as _forge_state_dir
    from engine.utils import json_io as _json_io

    candidate = _forge_state_dir(project_root) / "forge-pending.json"
    if not candidate.exists():
        return fallback
    try:
        return _json_io.read_json(candidate)
    except Exception:
        # Forensic — never mask the original adapter exception with a
        # secondary I/O error. Best-effort: return fallback so the
        # PausedForInputError still has a non-empty ``.intent``.
        return fallback


# --- ask -------------------------------------------------------------------


def ask(
    question: str,
    options: Mapping[str, str],
    *,
    default: str | None = None,
    allow_pause: bool = True,
    project_root: Path | None = None,
) -> str:
    """Single-select prompt. ``options`` is ``{key: human_label}``.

    Returns the chosen key. If no response is on disk, writes the
    canonical pending intent and raises ``PausedForInputError`` so the
    top-level handler can exit 2.

    Task 0.7b: body delegates to the resolved host adapter. The adapter
    handles the DRIFT-1 pending/response loop against ``.claude/forge/state/``
    (the v1.3 sub-namespace) and raises ``PausedForInputError`` /
    ``UserPausedError`` / ``UserCancelledError`` which this delegate
    wraps back to ``question.*`` equivalents so the cli.py exception
    ladder keeps working without changes.
    """
    if not options:
        raise ValueError("ask() requires at least one option")

    project_root = (
        project_root if project_root is not None else _project_root_for_io()
    )

    # Normaliza o default uma vez: só vale se for uma key real de options.
    # Compartilhado entre o intent legado e a chamada ao adapter pra não
    # divergir (DRY — comportamento idêntico ao cálculo duplicado anterior).
    effective_default = default if default in options else None

    # Build the legacy-shape intent dict so ``PausedForInputError.intent``
    # carries the same payload callers used to see. The adapter writes
    # its own (identical-shape) pending to disk; this dict is only for
    # the in-process exception attribute.
    intent = _build_pending(
        kind="ask",
        question_text=question,
        options=options,
        default=effective_default,
        allow_pause=allow_pause,
    )

    from engine.host.adapter import (
        AskKind,
        PausedForInputError as _AdapterPaused,
        UserPausedError as _AdapterUserPaused,
        UserCancelledError as _AdapterUserCancelled,
    )

    try:
        result = _resolve_adapter(project_root).ask(
            kind=AskKind.ASK,
            question=question,
            options=dict(options),
            default=effective_default,
            allow_pause=allow_pause,
        )
    except _AdapterPaused:
        # First entry — engine emitted fresh pending, no response yet.
        # Wrap as question.PausedForInputError so cli.main maps to exit 2
        # and callers' ``except question.PausedForInputError`` continues
        # working untouched. Re-hydrate ``.intent`` from the adapter's
        # on-disk pending so the surfaced ``intent-id`` matches what the
        # host will see (and what tests anchor responses against).
        raise PausedForInputError(
            intent=_read_adapter_pending_or_fallback(project_root, intent)
        )
    except _AdapterUserPaused:
        if not allow_pause:
            # Legacy semantic preserved: pause forbidden in this context.
            # State files remain on disk (CR-002 — adapter no longer
            # auto-clears) for forensic inspection.
            raise ValueError(
                "pause not allowed in this context, but response was paused"
            )
        raise UserPausedError("user paused via response")
    except _AdapterUserCancelled:
        raise UserCancelledError("user cancelled via response")

    value = result.value
    if not isinstance(value, str) or value not in options:
        # CR-002: state remains on disk — cli.py finally clears on terminal
        # error paths; here we just surface the validation failure.
        raise ValueError(
            f"response value {value!r} is not one of the offered options "
            f"{list(options.keys())!r}"
        )
    # Happy path — caller (cli.py finally) clears state. CR-002 invariant.
    return value


# --- ask_multi -------------------------------------------------------------


def ask_multi(
    question: str,
    options: Mapping[str, str],
    *,
    min_selected: int = 0,
    project_root: Path | None = None,
) -> list[str]:
    """Multi-select prompt. Returns picked keys in ``options`` insertion order.

    Response shape: ``value`` is a list of keys (the host orders them
    however it likes; the engine re-projects onto ``options`` order so
    downstream output stays stable regardless of input order).

    Task 0.7b: body delegates to the resolved host adapter; see ``ask``.
    """
    if not options:
        raise ValueError("ask_multi() requires at least one option")

    project_root = (
        project_root if project_root is not None else _project_root_for_io()
    )

    intent = _build_pending(
        kind="ask_multi",
        question_text=question,
        options=options,
        default=None,
        allow_pause=True,
        min_selected=min_selected,
    )

    from engine.host.adapter import (
        PausedForInputError as _AdapterPaused,
        UserPausedError as _AdapterUserPaused,
        UserCancelledError as _AdapterUserCancelled,
    )

    try:
        value = _resolve_adapter(project_root).ask_multi(
            question=question,
            options=dict(options),
            min_selected=min_selected,
        )
    except _AdapterPaused:
        raise PausedForInputError(
            intent=_read_adapter_pending_or_fallback(project_root, intent)
        )
    except _AdapterUserPaused:
        raise UserPausedError("user paused via response")
    except _AdapterUserCancelled:
        raise UserCancelledError("user cancelled via response")

    if not isinstance(value, list):
        # CR-002: preserve forensics — see ``ask`` rationale above.
        raise ValueError(
            f"ask_multi response value must be a list, got {type(value).__name__}"
        )

    picked = {str(v).lower() for v in value}
    valid_keys_lower = {k.lower() for k in options.keys()}
    invalid = picked - valid_keys_lower
    if invalid:
        # CR-002: preserve forensics.
        raise ValueError(f"invalid option keys: {sorted(invalid)!r}")
    result = [k for k in options.keys() if k.lower() in picked]
    if len(result) < min_selected:
        # CR-002: preserve forensics.
        raise ValueError(
            f"at least {min_selected} option(s) required, got {len(result)}"
        )
    # Happy path — caller (cli.py finally) clears state. CR-002 invariant.
    return result


# --- ask_text --------------------------------------------------------------


def ask_text(
    question: str,
    *,
    default: str | None = None,
    validator: Callable[[str], bool] | None = None,
    validator_hint: str | None = None,
    project_root: Path | None = None,
) -> str:
    """Free-text prompt with optional validator and default.

    Validator returns True on accept. If the response value fails the
    validator, the engine raises ``ValueError`` (it does not loop —
    looping is the host's responsibility, just like with ``ask``).

    Task 0.7b: body delegates to the resolved host adapter; see ``ask``.
    The Python-callable ``validator`` is applied post-consume in this
    delegate (the adapter only knows ``validator_hint`` over the wire).
    """
    project_root = (
        project_root if project_root is not None else _project_root_for_io()
    )

    intent = _build_pending(
        kind="ask_text",
        question_text=question,
        options=None,
        default=default,
        allow_pause=True,
        validator_hint=validator_hint,
    )

    from engine.host.adapter import (
        PausedForInputError as _AdapterPaused,
        UserPausedError as _AdapterUserPaused,
        UserCancelledError as _AdapterUserCancelled,
    )

    try:
        value = _resolve_adapter(project_root).ask_text(
            prompt=question,
            default=default,
            validator_hint=validator_hint,
        )
    except _AdapterPaused:
        raise PausedForInputError(
            intent=_read_adapter_pending_or_fallback(project_root, intent)
        )
    except _AdapterUserPaused:
        raise UserPausedError("user paused via response")
    except _AdapterUserCancelled:
        raise UserCancelledError("user cancelled via response")

    # Empty value with a default → resolve to default (legacy semantics).
    if (value is None or value == "") and default is not None:
        # Happy path — caller (cli.py finally) clears state.
        return default
    if not isinstance(value, str) or not value:
        # CR-002: preserve forensics on invalid response value.
        raise ValueError("ask_text response must carry a non-empty 'value' string")
    if validator is not None and not validator(value):
        # CR-002: preserve forensics on validator rejection.
        raise ValueError(validator_hint or f"validator rejected value {value!r}")
    # Happy path — caller (cli.py finally) clears state. CR-002 invariant.
    return value


# --- ask_three_paths -------------------------------------------------------


def ask_three_paths(
    gate_name: str,
    paths: Sequence[Mapping[str, str]],
) -> str:
    """Render the 3-caminhos prompt (discipline §1) and return the picked key.

    ``paths`` MUST be exactly 3 entries, each with ``label`` + ``motive``.
    The visual block itself is rendered by the host (Claude Code,
    opencode, or ``TtyAdapter`` on the TTY path) using the intent
    payload; this entrypoint only assembles the intent and consumes the
    response.
    """
    if len(paths) != 3:
        raise ValueError(
            f"ask_three_paths requires exactly 3 paths (discipline §1); got {len(paths)}"
        )

    options = {
        "a": paths[0]["label"],
        "b": paths[1]["label"],
        "c": paths[2]["label"],
    }
    # HI-001: carry the motives alongside the labels so the host can
    # render the canonical 3-caminhos block (discipline §1) — labels
    # alone leave the rendering anaemic. Schema documents this as an
    # ``ask_three_paths``-only optional field.
    keys = ("a", "b", "c")
    paths_detail = [
        {
            "key": keys[i],
            "label": str(paths[i].get("label", "")),
            "motive": str(paths[i].get("motive", "")),
        }
        for i in range(3)
    ]
    question_text = f"Qual caminho para resolver '{gate_name}'?"

    # Resolve the I/O anchor with the same fallback ``ask`` uses, so the
    # public signature ``ask_three_paths(gate_name, paths)`` stays intact
    # — no callsite needs to thread ``project_root`` through.
    project_root = _project_root_for_io()

    # In-process intent payload for ``PausedForInputError.intent`` parity
    # (the adapter writes its own identical-shape pending to disk).
    intent = _build_pending(
        kind="ask_three_paths",
        question_text=question_text,
        options=options,
        default=None,
        allow_pause=True,
        paths_detail=paths_detail,
    )

    from engine.host.adapter import (
        AskKind,
        PausedForInputError as _AdapterPaused,
        UserPausedError as _AdapterUserPaused,
        UserCancelledError as _AdapterUserCancelled,
    )

    try:
        result = _resolve_adapter(project_root).ask(
            kind=AskKind.ASK_THREE_PATHS,
            question=question_text,
            options=dict(options),
            default=None,
            allow_pause=True,
            paths_detail=paths_detail,
        )
    except _AdapterPaused:
        # First entry — re-hydrate ``.intent`` from the adapter's on-disk
        # pending so the surfaced intent-id matches what the host sees.
        raise PausedForInputError(
            intent=_read_adapter_pending_or_fallback(project_root, intent)
        )
    except _AdapterUserPaused:
        raise UserPausedError("user paused via response")
    except _AdapterUserCancelled:
        raise UserCancelledError("user cancelled via response")

    value = result.value
    if not isinstance(value, str) or value not in options:
        # CR-002: state remains on disk for forensic inspection; cli.py
        # finally clears on terminal error paths.
        raise ValueError(
            f"ask_three_paths response value {value!r} is not one of 'a'/'b'/'c'"
        )
    # Happy path — caller (cli.py finally) clears state. CR-002 invariant.
    return value


# --- confirm ---------------------------------------------------------------


def confirm(question: str, *, default: bool = False, allow_pause: bool = True) -> bool:
    """Yes/no prompt. Returns True for sim, False for não.

    The response may carry either a boolean ``value`` (canonical) or a
    legacy ``"s"`` / ``"n"`` string — both are accepted because the
    spec § 2.2 explicitly types ``value`` as ``str | list[str] | bool``.

    ``allow_pause`` segue o canônico do módulo (default ``True``,
    mesma semântica de ``ask``). O master review #18 do PR #11
    apontou drift entre SPEC §2.1 (exemplo com ``allow-pause: false``)
    e a implementação anterior que hard-codava ``True``. A decisão
    foi declarar a IMPL como canônica e fixar o default via
    regression test em ``test_ui_question_api_signatures.py``.
    """
    default_key = "s" if default else "n"
    options = {"s": "sim", "n": "não"}

    # Resolve the I/O anchor with the same fallback ``ask`` uses, keeping
    # the public signature ``confirm(question, *, default, allow_pause)``
    # intact — no callsite threads ``project_root`` through.
    project_root = _project_root_for_io()

    # In-process intent payload for ``PausedForInputError.intent`` parity
    # (the adapter writes its own identical-shape pending to disk).
    intent = _build_pending(
        kind="confirm",
        question_text=question,
        options=options,
        default=default_key,
        allow_pause=allow_pause,
    )

    from engine.host.adapter import (
        AskKind,
        PausedForInputError as _AdapterPaused,
        UserPausedError as _AdapterUserPaused,
        UserCancelledError as _AdapterUserCancelled,
    )

    try:
        result = _resolve_adapter(project_root).ask(
            kind=AskKind.CONFIRM,
            question=question,
            options=dict(options),
            default=default_key,
            allow_pause=allow_pause,
        )
    except _AdapterPaused:
        raise PausedForInputError(
            intent=_read_adapter_pending_or_fallback(project_root, intent)
        )
    except _AdapterUserPaused:
        if not allow_pause:
            # Legacy semantic preserved: pause forbidden in this context.
            # State files remain on disk (CR-002) for forensic inspection.
            raise ValueError(
                "pause not allowed in this context, but response was paused"
            )
        raise UserPausedError("user paused via response")
    except _AdapterUserCancelled:
        raise UserCancelledError("user cancelled via response")

    value = result.value
    if isinstance(value, bool):
        # Happy path — caller (cli.py finally) clears state. CR-002 invariant.
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"s", "sim", "y", "yes", "true"}:
            return True
        if normalized in {"n", "não", "nao", "no", "false"}:
            return False
    # CR-002: preserve forensics on unrecognised confirm value.
    raise ValueError(
        f"confirm response value {value!r} is not a bool or recognised yes/no token"
    )
