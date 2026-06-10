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
  ``ask_three_paths`` keep their exact signatures. 106 callsites across
  10 engine modules continue to compile and run untouched.
- ``PromptAbortedError`` / ``NonInteractiveError`` still ship from this
  module (callers ``except`` them).
- ``_PAUSE_TOKENS`` (``para``, ``pausa``, ``quit``, ``q``, ``exit``) keep
  their values — the tokens are recognised on the response side now,
  not on stdin.
- ``allow_pause=False`` semantics preserved: a paused response raises
  ``ValueError`` (pause forbidden in this context).

Refs:
- docs/superpowers/specs/drift-1-intent-protocol.md §2, §3, §4, §6
- docs/schemas/intent-protocol.md
- docs/superpowers/plans/drift-1-intent-protocol.md W2.T1
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from engine.ui import intent_state
from engine.utils.paths import try_find_project_root


class PromptAbortedError(RuntimeError):
    """Raised when the user types ``para`` / ``quit`` at a prompt that allows it.

    Pre-DRIFT-1 this fired off a stdin read; post-DRIFT-1 it fires when
    the response file carries ``"paused": true`` and ``allow_pause`` is
    True. Same semantics, different wire.
    """


class NonInteractiveError(RuntimeError):
    """Raised when a prompt fires without a response and pause is forbidden.

    Kept for API stability — callers may still ``except NonInteractiveError``.
    DRIFT-1 superseded the stdin-EOF path that used to raise it; the
    sentinel is now reached via ``allow_pause=False`` + ``paused: true``
    on the response.
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
    """

    intent: dict[str, Any]

    def __init__(self, *, intent: dict[str, Any]) -> None:
        super().__init__(f"forge paused awaiting input (intent-id={intent.get('intent-id')!r})")
        self.intent = intent


_PAUSE_TOKENS = {"para", "pausa", "quit", "q", "exit"}

_SCHEMA_VERSION = 1


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
    """Best-effort recovery of (command, command-args) from ``sys.argv``.

    Pre-condition: the engine is invoked via ``forge <command> [...]``
    or ``python -m engine.cli <command> [...]``. When neither matches
    (tests calling ``question.ask`` directly), we fall back to the
    module name + empty args. The pending JSON keeps the field
    populated so the caller has *some* context, even in degenerate runs.
    """
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
) -> dict[str, Any]:
    """Assemble the canonical pending payload (matches docs/schemas/intent-protocol.md)."""
    command, command_args = _command_context()
    intent: dict[str, Any] = {
        "schema-version": _SCHEMA_VERSION,
        "intent-id": _stable_intent_id(
            kind,
            question_text,
            options,
            extra={"default": default, "min-selected": min_selected},
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
    return intent


def _emit_pending_and_raise(intent: dict[str, Any]) -> None:
    """Write the pending file (after race detection) and raise the sentinel.

    Race detection consults ``.claude/state/forge-pending.json``; a recent
    pending with a different intent-id raises ``RaceDetectedError`` from
    ``intent_state`` (caught upstream and mapped to exit 1 by spec §3).
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
    """Apply the pause-token semantics to a response.

    - ``paused: true`` + ``allow_pause=True`` → raise ``PromptAbortedError``.
    - ``paused: true`` + ``allow_pause=False`` → raise ``ValueError``.
    - ``cancelled: true`` is treated like pause-with-allow (legacy: 130
      path) — preserved for the spec's cancellation channel.
    """
    if response.get("paused"):
        _clear_state()
        if allow_pause:
            raise PromptAbortedError("user paused via response")
        raise ValueError("pause not allowed in this context, but response was paused")
    if response.get("cancelled"):
        _clear_state()
        raise PromptAbortedError("user cancelled via response")


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

    # Defensive: _emit_pending_and_raise always raises, but the type
    # checker doesn't know that — fall through here only when response
    # is present.
    _check_pause_response(response, allow_pause=allow_pause)

    value = response.get("value")
    if not isinstance(value, str) or value not in options:
        _clear_state()
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
        _clear_state()
        raise ValueError(f"ask_multi response value must be a list, got {type(value).__name__}")

    picked = {str(v).lower() for v in value}
    valid_keys_lower = {k.lower() for k in options.keys()}
    invalid = picked - valid_keys_lower
    if invalid:
        _clear_state()
        raise ValueError(f"invalid option keys: {sorted(invalid)!r}")
    result = [k for k in options.keys() if k.lower() in picked]
    if len(result) < min_selected:
        _clear_state()
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
        _clear_state()
        raise ValueError("ask_text response must carry a non-empty 'value' string")
    if validator is not None and not validator(value):
        _clear_state()
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
    intent = _build_pending(
        kind="ask_three_paths",
        question_text=f"Qual caminho para resolver '{gate_name}'?",
        options=options,
        default=None,
        allow_pause=True,
    )

    response = _consume_response_or_none(intent["intent-id"])
    if response is None:
        _emit_pending_and_raise(intent)

    _check_pause_response(response, allow_pause=True)

    value = response.get("value")
    if not isinstance(value, str) or value not in options:
        _clear_state()
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
    _clear_state()
    raise ValueError(
        f"confirm response value {value!r} is not a bool or recognised yes/no token"
    )
