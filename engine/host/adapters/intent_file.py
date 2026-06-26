"""IntentFileAdapter — fallback DRIFT-1 adapter against ``.claude/forge/state/``.

Spec: ``docs/superpowers/specs/2026-06-16-v1-3-pilot-ready-design.md`` §4.

Thin facade over ``engine.ui.intent_state`` parameterised by ``state_dir``.
When no native host adapter is detected (claude-code, opencode, tty),
the registry falls back to this adapter so any harness with read/write
access to ``.claude/forge/state/`` can drive ``forge`` via the DRIFT-1
file protocol.

Why this is a thin facade (Task 0.5 contract):

- ``intent_state`` already implements the full DRIFT-1 surface: atomic
  pending/response writes, schema-version guard, race detection, the
  consumed-intent log for re-entry idempotency. Re-implementing any of
  that here would just create a second source of truth.
- The adapter only needs to:
  1. Compose the canonical pending payload (kebab-case keys per
     ``docs/schemas/intent-protocol.md``, identical shape to what
     ``engine.ui.question._build_pending`` emits in the native path).
  2. Generate a deterministic ``intent-id`` so re-invocation of the
     same prompt lines up with the response on disk.
  3. Plumb ``state_dir=forge_state_dir(project_root)`` through every
     ``intent_state`` call so the v1.3 sub-namespace
     ``.claude/forge/state/`` is honoured.

Task 0.7a (parity-with-question hardening): adapter now accepts
``min_selected`` / ``validator_hint`` / ``paths_detail`` extras and
resolves ``(command, command_args)`` via ``_command_context()`` (the same
contextvar→sys.argv ladder ``question._build_pending`` uses). This
unblocks Task 0.7b (question.py delegate refactor) by guaranteeing
intent-id stability and pending-shape parity bit-a-bit with the native
path.

Callsites (``engine/ui/question.py`` and friends) chamam ``intent_state``
sem ``state_dir``; o default resolve pra ``.claude/forge/state/`` (anchor
canônico v1.3 via ``forge_state_dir``). O anchor legado ``.claude/state/``
foi aposentado — não há mais divergência de raia entre os callsites.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.host.adapter import (
    AskKind,
    AskResult,
    HostAdapter,
    HostName,
    PausedForInputError,
    UserCancelledError,
    UserPausedError,
)
from engine.ui import intent_state
from engine.ui.question import stable_intent_id
from engine.utils.paths import forge_state_dir


# Wire-format version mirror — must match ``intent_state._SCHEMA_VERSION``.
# Kept in sync via test (changes to either side must bump the other);
# importing the private constant would couple us to ``intent_state``'s
# internals more tightly than the rest of this facade.
_SCHEMA_VERSION = 1


def _now_iso() -> str:
    """UTC timestamp in the same format ``question._now_iso`` uses."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class IntentFileAdapter(HostAdapter):
    """Fallback adapter that drives DRIFT-1 against the v1.3 sub-namespace.

    Construction is cheap; the adapter holds only ``project_root`` and a
    cached ``state_dir`` so every method passes the same anchor through
    to ``intent_state``.
    """

    name = HostName.INTENT_FILE

    def __init__(self, *, project_root: Path):
        self.project_root = Path(project_root)
        self._state_dir = forge_state_dir(self.project_root)

    # ------------------------------------------------------------------
    # ask / ask_text / ask_multi — DRIFT-1 pending/response loop
    # ------------------------------------------------------------------

    def ask(
        self,
        *,
        kind: AskKind,
        question: str,
        options: dict,
        default: str | None,
        allow_pause: bool,
        min_selected: int | None = None,
        validator_hint: str | None = None,
        paths_detail: list[dict[str, str]] | None = None,
    ) -> AskResult:
        return self._ask_loop(
            kind=kind,
            question=question,
            options=options or {},
            default=default,
            allow_pause=allow_pause,
            min_selected=min_selected,
            validator_hint=validator_hint,
            paths_detail=paths_detail,
        )

    def ask_text(
        self,
        *,
        prompt: str,
        default: str | None,
        validator_hint: str | None = None,
    ) -> str:
        result = self._ask_loop(
            kind=AskKind.ASK_TEXT,
            question=prompt,
            options={},
            default=default,
            allow_pause=True,
            validator_hint=validator_hint,
        )
        value = result.value
        if isinstance(value, list):
            # ``ask_text`` callers contract a string — flatten defensively.
            return value[0] if value else ""
        return str(value) if value is not None else (default or "")

    def ask_multi(
        self,
        *,
        question: str,
        options: dict,
        min: int = 0,
        max: int | None = None,
        min_selected: int | None = None,
    ) -> list[str]:
        result = self._ask_loop(
            kind=AskKind.ASK_MULTI,
            question=question,
            options=options or {},
            default=None,
            allow_pause=True,
            min_selected=min_selected,
        )
        value = result.value
        if isinstance(value, list):
            return value
        if value is None:
            return []
        # Defensive single→list flatten — host should send list, but a
        # scalar response is recoverable.
        return [str(value)]

    # ------------------------------------------------------------------
    # emit_progress / emit_warn — non-blocking channels
    # ------------------------------------------------------------------

    def emit_progress(self, *, step: str, total: int, current: int) -> None:
        # Non-blocking by design. The intent-file fallback has no
        # progress channel and stderr noise would pollute hosts that
        # parse subprocess output. Hosts with a real UI override this.
        return None

    def emit_warn(self, *, message: str) -> None:
        # Non-blocking by design. Same rationale as ``emit_progress``;
        # warnings travel back via the next pending payload's metadata
        # rather than out-of-band stderr in this fallback.
        return None

    # ------------------------------------------------------------------
    # classify — intent-kind classify (reusa primitivos, NAO _ask_loop)
    # ------------------------------------------------------------------

    def classify(
        self,
        *,
        fragments: list[dict],
        schema: dict,
    ) -> list[dict] | None:
        """Classify rule fragments via the DRIFT-1 pending/response loop.

        Reuses the low-level primitives (``stable_intent_id``,
        ``intent_state.read_response``, ``pending_lock``,
        ``detect_race``, ``write_pending``) but NOT ``_ask_loop`` —
        classify has a richer payload (fragments + classification-schema)
        and a structured return (``list[dict]``) that does not fit the
        ``AskResult(value: str|list[str])`` contract of the ask-shaped
        methods.

        Re-entry: the same ``(fragments, schema)`` tuple produces the
        same ``intent_id`` across re-invocations, so a re-run after the
        host writes the response will consume via the log and return the
        ``classification`` list directly.
        """
        command, command_args = self._resolve_command_context()
        intent_id = stable_intent_id(
            kind=AskKind.CLASSIFY.value,
            question_text="classify-rules",
            options={},
            extra={"fragments": fragments, "schema": schema},
            command=command,
            command_args=command_args,
        )
        existing = intent_state.read_response(
            self.project_root, intent_id, state_dir=self._state_dir
        )
        if existing is not None:
            if existing.get("cancelled") is True:
                raise UserCancelledError(
                    f"user cancelled (intent-id={intent_id})"
                )
            if existing.get("paused") is True:
                raise UserPausedError(
                    f"user paused (intent-id={intent_id})"
                )
            return existing.get("classification")
        intent = {
            "schema-version": _SCHEMA_VERSION,
            "kind": AskKind.CLASSIFY.value,
            "intent-id": intent_id,
            "command": command,
            "command-args": list(command_args),
            "fragments": fragments,
            "classification-schema": schema,
            "created-at": _now_iso(),
            "pid": os.getpid(),
        }
        with intent_state.pending_lock(
            self.project_root, state_dir=self._state_dir
        ):
            intent_state.detect_race(
                self.project_root,
                new_intent_id=intent_id,
                state_dir=self._state_dir,
            )
            intent_state.write_pending(
                intent, self.project_root, state_dir=self._state_dir
            )
        raise PausedForInputError(
            f"forge paused awaiting classify (intent-id={intent_id})"
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_command_context(self) -> tuple[str, list[str]]:
        """Defer to ``engine.ui.question._command_context`` for HI-002 parity.

        Lazy import keeps the adapter→question dependency direction
        one-way (adapter already imports ``stable_intent_id`` from
        ``question``, but we localise the second import to keep the
        module-level surface lean and avoid widening the import graph at
        load time). The contextvar lookup itself is cheap.
        """
        from engine.ui.question import _command_context

        return _command_context()

    def _ask_loop(
        self,
        *,
        kind: AskKind,
        question: str,
        options: dict,
        default: str | None,
        allow_pause: bool,
        min_selected: int | None = None,
        validator_hint: str | None = None,
        paths_detail: list[dict[str, str]] | None = None,
    ) -> AskResult:
        """Shared DRIFT-1 loop body — re-entry consume OR first-entry emit.

        Deterministic ``intent-id`` derived from the canonical
        ``stable_intent_id`` helper means the same ``(kind, question,
        options, command-context)`` tuple produces the same id across
        re-invocations, which is what makes the consume path safe.

        Hash extras (``min-selected``, ``validator-hint``, ``paths-detail``)
        match ``question._build_pending``'s ``extra_for_hash`` shape so
        the adapter and the native path produce identical intent-ids for
        identical inputs. ``paths-detail`` is OMITTED from the hash dict
        when ``None`` (MD-fix #11 parity) — including it as ``None`` here
        would diverge from question.py and break re-entry across paths.
        """
        command, command_args = self._resolve_command_context()

        extra_for_hash: dict[str, Any] = {
            "default": default,
            "min-selected": min_selected,
            "validator-hint": validator_hint,
        }
        if paths_detail is not None:
            extra_for_hash["paths-detail"] = [dict(item) for item in paths_detail]

        intent_id = stable_intent_id(
            kind=kind.value,
            question_text=question,
            options=options,
            extra=extra_for_hash,
            command=command,
            command_args=command_args,
        )

        # Re-entry: response already waiting? Returns ``None`` when the
        # caller is about to write the FIRST pending of its lifecycle.
        existing = intent_state.read_response(
            self.project_root,
            intent_id,
            state_dir=self._state_dir,
        )
        if existing is not None:
            # CR-001 / CR-003 — propagate pause/cancel intent as
            # exceptions instead of silently coercing to AskResult.
            # Pre-0.7c the adapter dropped these flags on the floor;
            # question.py's post-delegate could not tell pause/cancel
            # apart from a malformed response.
            #
            # State is left in place on these paths: the cleanup
            # responsibility lives in ``engine.cli`` finally (CR-002 —
            # forensic preservation across error paths). The
            # consumed-intent log entry, if present, also remains so
            # repeated re-entries are idempotent.
            if existing.get("cancelled") is True:
                raise UserCancelledError(
                    f"user cancelled (intent-id={intent_id})"
                )
            if existing.get("paused") is True:
                raise UserPausedError(
                    f"user paused (intent-id={intent_id})"
                )
            # Happy path: return the value but DO NOT auto-clear state
            # files. CR-002 — caller (cli.py finally) clears via
            # ``intent_state.clear_intent_log_only`` (or equivalent)
            # AFTER post-delegate validation has accepted the response.
            # Clearing here would prevent question.py's
            # ``value not in options`` rejection from preserving
            # forensic state for inspection.
            value = existing.get("value")
            return AskResult(value=value, from_default=False, paused=False)

        # First entry: build canonical pending, detect_race, emit,
        # raise the paused sentinel for the engine to bubble up as
        # exit code 2.
        intent = self._build_pending(
            intent_id=intent_id,
            kind=kind,
            question=question,
            options=options,
            default=default,
            allow_pause=allow_pause,
            command=command,
            command_args=command_args,
            min_selected=min_selected,
            validator_hint=validator_hint,
            paths_detail=paths_detail,
        )
        # C4 CONC-1 (B): a seção crítica detect_race+write_pending roda sob
        # lock exclusivo por-root. Fecha a janela TOCTOU em que dois processos
        # forge ambos passam pelo detect_race (pending ausente) antes de
        # qualquer escrita. O lock file é dedicado (forge-pending.lock), não o
        # próprio pending.json — ver intent_state.pending_lock.
        with intent_state.pending_lock(
            self.project_root, state_dir=self._state_dir
        ):
            intent_state.detect_race(
                self.project_root,
                new_intent_id=intent_id,
                state_dir=self._state_dir,
            )
            intent_state.write_pending(
                intent,
                self.project_root,
                state_dir=self._state_dir,
            )
        raise PausedForInputError(
            f"forge paused awaiting host response (intent-id={intent_id})"
        )

    def _build_pending(
        self,
        *,
        intent_id: str,
        kind: AskKind,
        question: str,
        options: dict,
        default: str | None,
        allow_pause: bool,
        command: str,
        command_args: list[str],
        min_selected: int | None = None,
        validator_hint: str | None = None,
        paths_detail: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Assemble the canonical pending payload.

        Shape matches ``docs/schemas/intent-protocol.md`` and what
        ``engine.ui.question._build_pending`` emits in the native path.
        Keys are kebab-case on the wire by design — pre-existing host
        clients (and ``intent_state._check_schema_version``) already
        consume that shape.

        Task 0.7a parity: ``command``/``command_args`` come from
        ``_command_context()`` (resolved by ``_ask_loop``), NOT the
        ``("host-adapter", [])`` placeholder used pre-0.7a. This honours
        the HI-002 invariant — ``pending["command"]`` reflects the
        ``cli.main`` argv that drove the current invocation.

        Optional fields (``validator-hint``, ``min-selected``,
        ``paths-detail``) are present in the payload ONLY when not None,
        matching ``question._build_pending`` lines 367-372. Including
        them as ``None`` would diverge from the native path and pollute
        the wire format for hosts that key on ``"validator-hint" in payload``.
        """
        intent: dict[str, Any] = {
            "schema-version": _SCHEMA_VERSION,
            "intent-id": intent_id,
            "command": command,
            "command-args": list(command_args),
            "kind": kind.value,
            "question": question,
            "options": dict(options) if options else {},
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
