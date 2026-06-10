"""Interactive prompts — the engine-side chokepoint of the DRIFT-1 intent protocol.

Originally this module bridged subcommands to ``sys.stdin``. Post DRIFT-1
W2 (spec ``docs/superpowers/specs/drift-1-intent-protocol.md``) it does
the opposite: each ``ask*`` entrypoint either consumes a matching response
from ``.claude/state/forge-response.json`` (returning the value) or emits
a canonical pending intent to ``.claude/state/forge-pending.json`` and
raises ``PausedForInputError``. The top-level handler in ``engine.cli``
maps that sentinel to exit code 2.

stdin reading lives in ``engine.ui.tty_bridge`` (W3), which loops over
``engine.cli`` in subprocess mode whenever the dispatcher detects a real
terminal (sub-Q **Sd** of the spec). No subcommand calls stdin directly —
this module is the single point of input.

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
from typing import Any, Callable, Mapping, NoReturn, Sequence

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
    on the response (which raises ``ValueError`` directly — see
    ``_check_pause_response``).
    """


class PausedForInputError(Exception):
    """Sentinel raised by the chokepoint when no response is available yet.

    ``intent`` carries the dict that was just written to
    ``.claude/state/forge-pending.json`` — the host caller (Claude Code
    or ``engine.ui.tty_bridge``) reads that file and writes a response;
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


# --- _read_line — superseded by engine.ui.tty_bridge (W3) ------------------
#
# The pre-DRIFT-1 implementation of ``_read_line`` read from ``sys.stdin``
# directly. That logic moves to ``engine/ui/tty_bridge.py`` in W3 so the
# engine itself never touches the wire. Keeping the helper name as a
# stub-with-explanation prevents accidental reintroduction of stdin
# reading inside ``question.py``.


def _read_line(prompt: str, *, stream: Any = None) -> str:  # pragma: no cover
    """Removed in DRIFT-1 W2. stdin handling lives in
    ``engine.ui.tty_bridge`` (W3). Calling this on the engine side is a
    programming error — the engine emits intent and exits 2; only the
    tty_bridge loop talks to stdin.
    """
    raise NotImplementedError(
        "engine.ui.question no longer reads stdin. "
        "Input flows through .claude/state/forge-{pending,response}.json — "
        "see engine.ui.tty_bridge for the TTY fallback loop (W3)."
    )


# --- Intent-id derivation --------------------------------------------------


def _stable_intent_id(
    kind: str,
    question_text: str,
    options: Mapping[str, str] | None,
    extra: Mapping[str, Any] | None = None,
) -> str:
    """Deterministic intent-id for the (kind, question, options) tuple.

    A stable id lets a re-invocation of the same command + same prompt
    line up with the response on disk without callers having to thread
    an explicit id through their signatures (which would break the
    invariant in the module docstring). The id is *not* a security
    token — it is a wire correlation key.

    The shape is a UUID-formatted SHA-256 prefix: 8-4-4-4-12 hex chars,
    32 hex digits total. UUID format is what the spec § 2.1 example
    declares; using a hash instead of ``uuid.uuid4()`` makes the id
    reproducible across process restarts.
    """
    payload = json.dumps(
        {
            "kind": kind,
            "question": question_text,
            "options": dict(options) if options is not None else None,
            "extra": dict(extra) if extra is not None else None,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
    return f"{digest[0:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:32]}"


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

    The ``extra`` mapping fed into ``_stable_intent_id`` includes
    ``validator-hint`` (MD-001 fix from W2 review): two ``ask_text``
    calls with the same prompt but different validators MUST produce
    distinct intent-ids, otherwise a stale response intended for
    validator A could be consumed by a call expecting validator B.
    The validator callable itself is not deterministically hashable;
    ``validator_hint`` is the public-facing proxy and is stable enough
    for wire correlation.
    """
    command, command_args = _command_context()
    intent: dict[str, Any] = {
        "schema-version": _SCHEMA_VERSION,
        "intent-id": _stable_intent_id(
            kind,
            question_text,
            options,
            extra={
                "default": default,
                "min-selected": min_selected,
                "validator-hint": validator_hint,
            },
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


def _emit_pending_and_raise(intent: dict[str, Any]) -> NoReturn:
    """Write the pending file (after race detection) and raise the sentinel.

    Race detection consults ``.claude/state/forge-pending.json``; a recent
    pending with a different intent-id raises ``RaceDetectedError`` from
    ``intent_state`` (caught upstream and mapped to exit 1 by spec §3).

    The ``NoReturn`` annotation (LO-002 fix) lets type checkers — and
    static-analysis readers — know that control never returns from this
    function; the downstream entrypoints rely on that to keep their
    happy-path branches readable without defensive guards.
    """
    project_root = _project_root_for_io()
    intent_state.detect_race(project_root, new_intent_id=intent["intent-id"])
    intent_state.write_pending(intent, project_root)
    raise PausedForInputError(intent=intent)


def _consume_response_or_none(intent_id: str) -> dict[str, Any] | None:
    """Read the response file if it exists and its intent-id matches."""
    project_root = _project_root_for_io()
    return intent_state.read_response(project_root, intent_id=intent_id)


def _clear_state() -> None:
    intent_state.clear_intent_files(_project_root_for_io())


def _check_pause_response(
    response: dict[str, Any],
    *,
    allow_pause: bool,
) -> None:
    """Apply the pause / cancel semantics to a response.

    Resolution order (MD-002 fix from W2 review): cancel is checked
    BEFORE pause because cancellation is the stronger semantic. A
    malformed host response carrying both ``"cancelled": true`` and
    ``"paused": true`` resolves to cancellation — the user wants out
    entirely, not a resumable pause.

    Outcomes (each maps cleanly via ``engine.cli::main()``):

    - ``cancelled: true`` → ``_clear_state()`` then raise
      ``UserCancelledError`` (cli maps to exit 130, SPEC §8).
    - ``paused: true`` + ``allow_pause=True`` → ``_clear_state()`` then
      raise ``UserPausedError`` (cli maps to exit 2). This is the
      user-initiated pause channel — distinct from
      ``PausedForInputError`` (which fires when the engine emits a
      fresh pending and is still waiting for a first response).
    - ``paused: true`` + ``allow_pause=False`` → raise ``ValueError``
      (pause forbidden in this context). State files are NOT cleared:
      this is an invalid pause attempt, so the response is preserved
      forensically per SPEC §3.

    No ``RuntimeError`` ladder catches the new sentinels — they are
    plain ``Exception`` siblings of ``PausedForInputError``, so legacy
    ``except PromptAbortedError`` / ``except RuntimeError`` clauses in
    callsite modules cannot silently swallow user-initiated termination.
    """
    if response.get("cancelled"):
        _clear_state()
        raise UserCancelledError("user cancelled via response")
    if response.get("paused"):
        if allow_pause:
            _clear_state()
            raise UserPausedError("user paused via response")
        raise ValueError("pause not allowed in this context, but response was paused")


# --- ask -------------------------------------------------------------------


def ask(
    question: str,
    options: Mapping[str, str],
    *,
    default: str | None = None,
    allow_pause: bool = True,
) -> str:
    """Single-select prompt. ``options`` is ``{key: human_label}``.

    Returns the chosen key. If no response is on disk, writes the
    canonical pending intent and raises ``PausedForInputError`` so the
    top-level handler can exit 2.
    """
    if not options:
        raise ValueError("ask() requires at least one option")

    intent = _build_pending(
        kind="ask",
        question_text=question,
        options=options,
        default=default if default in options else None,
        allow_pause=allow_pause,
    )

    response = _consume_response_or_none(intent["intent-id"])
    if response is None:
        _emit_pending_and_raise(intent)

    _check_pause_response(response, allow_pause=allow_pause)

    value = response.get("value")
    if not isinstance(value, str) or value not in options:
        # CR-002: do NOT clear state on invalid value — preserve forensics
        # per SPEC §3 so the host can inspect what arrived.
        raise ValueError(
            f"response value {value!r} is not one of the offered options "
            f"{list(options.keys())!r}"
        )
    _clear_state()
    return value


# --- ask_multi -------------------------------------------------------------


def ask_multi(
    question: str,
    options: Mapping[str, str],
    *,
    min_selected: int = 0,
) -> list[str]:
    """Multi-select prompt. Returns picked keys in ``options`` insertion order.

    Response shape: ``value`` is a list of keys (the host orders them
    however it likes; the engine re-projects onto ``options`` order so
    downstream output stays stable regardless of input order).
    """
    if not options:
        raise ValueError("ask_multi() requires at least one option")

    intent = _build_pending(
        kind="ask_multi",
        question_text=question,
        options=options,
        default=None,
        allow_pause=True,
        min_selected=min_selected,
    )

    response = _consume_response_or_none(intent["intent-id"])
    if response is None:
        _emit_pending_and_raise(intent)

    _check_pause_response(response, allow_pause=True)

    value = response.get("value")
    if not isinstance(value, list):
        # CR-002: preserve forensics — see ``ask`` rationale above.
        raise ValueError(f"ask_multi response value must be a list, got {type(value).__name__}")

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
    _clear_state()
    return result


# --- ask_text --------------------------------------------------------------


def ask_text(
    question: str,
    *,
    default: str | None = None,
    validator: Callable[[str], bool] | None = None,
    validator_hint: str | None = None,
) -> str:
    """Free-text prompt with optional validator and default.

    Validator returns True on accept. If the response value fails the
    validator, the engine raises ``ValueError`` (it does not loop —
    looping is the host's responsibility, just like with ``ask``).
    """
    intent = _build_pending(
        kind="ask_text",
        question_text=question,
        options=None,
        default=default,
        allow_pause=True,
        validator_hint=validator_hint,
    )

    response = _consume_response_or_none(intent["intent-id"])
    if response is None:
        _emit_pending_and_raise(intent)

    _check_pause_response(response, allow_pause=True)

    value = response.get("value")
    # Empty value with a default → resolve to default (legacy semantics).
    if (value is None or value == "") and default is not None:
        _clear_state()
        return default
    if not isinstance(value, str) or not value:
        # CR-002: preserve forensics on invalid response value.
        raise ValueError("ask_text response must carry a non-empty 'value' string")
    if validator is not None and not validator(value):
        # CR-002: preserve forensics on validator rejection.
        raise ValueError(validator_hint or f"validator rejected value {value!r}")
    _clear_state()
    return value


# --- ask_three_paths -------------------------------------------------------


def ask_three_paths(
    gate_name: str,
    paths: Sequence[Mapping[str, str]],
) -> str:
    """Render the 3-caminhos prompt (discipline §1) and return the picked key.

    ``paths`` MUST be exactly 3 entries, each with ``label`` + ``motive``.
    The visual block itself is rendered by the host (Claude Code or
    ``engine.ui.tty_bridge``) using the intent payload; this entrypoint
    only assembles the intent and consumes the response.
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
    intent = _build_pending(
        kind="ask_three_paths",
        question_text=f"Qual caminho para resolver '{gate_name}'?",
        options=options,
        default=None,
        allow_pause=True,
        paths_detail=paths_detail,
    )

    response = _consume_response_or_none(intent["intent-id"])
    if response is None:
        _emit_pending_and_raise(intent)

    _check_pause_response(response, allow_pause=True)

    value = response.get("value")
    if not isinstance(value, str) or value not in options:
        # CR-002: preserve forensics on invalid path key.
        raise ValueError(
            f"ask_three_paths response value {value!r} is not one of 'a'/'b'/'c'"
        )
    _clear_state()
    return value


# --- confirm ---------------------------------------------------------------


def confirm(question: str, *, default: bool = False) -> bool:
    """Yes/no prompt. Returns True for sim, False for não.

    The response may carry either a boolean ``value`` (canonical) or a
    legacy ``"s"`` / ``"n"`` string — both are accepted because the
    spec § 2.2 explicitly types ``value`` as ``str | list[str] | bool``.
    """
    default_key = "s" if default else "n"
    options = {"s": "sim", "n": "não"}

    intent = _build_pending(
        kind="confirm",
        question_text=question,
        options=options,
        default=default_key,
        allow_pause=True,
    )

    response = _consume_response_or_none(intent["intent-id"])
    if response is None:
        _emit_pending_and_raise(intent)

    _check_pause_response(response, allow_pause=True)

    value = response.get("value")
    if isinstance(value, bool):
        _clear_state()
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"s", "sim", "y", "yes", "true"}:
            _clear_state()
            return True
        if normalized in {"n", "não", "nao", "no", "false"}:
            _clear_state()
            return False
    # CR-002: preserve forensics on unrecognised confirm value.
    raise ValueError(
        f"confirm response value {value!r} is not a bool or recognised yes/no token"
    )
