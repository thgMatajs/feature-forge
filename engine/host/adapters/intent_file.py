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

Legacy callsites (``engine/ui/question.py`` and friends) continue to
call ``intent_state`` without ``state_dir`` and keep writing to the
legacy ``.claude/state/`` anchor — Task 0.7 unifies them later.
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
    ) -> AskResult:
        return self._ask_loop(
            kind=kind,
            question=question,
            options=options or {},
            default=default,
            allow_pause=allow_pause,
        )

    def ask_text(self, *, prompt: str, default: str | None) -> str:
        result = self._ask_loop(
            kind=AskKind.ASK_TEXT,
            question=prompt,
            options={},
            default=default,
            allow_pause=True,
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
    ) -> list[str]:
        result = self._ask_loop(
            kind=AskKind.ASK_MULTI,
            question=question,
            options=options or {},
            default=None,
            allow_pause=True,
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
    # Internal helpers
    # ------------------------------------------------------------------

    def _ask_loop(
        self,
        *,
        kind: AskKind,
        question: str,
        options: dict,
        default: str | None,
        allow_pause: bool,
    ) -> AskResult:
        """Shared DRIFT-1 loop body — re-entry consume OR first-entry emit.

        Deterministic ``intent-id`` derived from the canonical
        ``stable_intent_id`` helper means the same ``(kind, question,
        options, command-context)`` tuple produces the same id across
        re-invocations, which is what makes the consume path safe.
        """
        intent_id = stable_intent_id(
            kind=kind.value,
            question_text=question,
            options=options,
            extra={
                "default": default,
                # Match the ``extra_for_hash`` shape used by
                # ``question._build_pending`` so the adapter and the
                # native path stay interchangeable from the host's
                # perspective. Adapter path does not surface
                # validator-hint / min-selected / paths-detail today;
                # passing ``None`` for both preserves parity bit-for-bit
                # with the legacy callsites that also pass ``None``.
                "min-selected": None,
                "validator-hint": None,
            },
        )

        # Re-entry: response already waiting? Returns ``None`` when the
        # caller is about to write the FIRST pending of its lifecycle.
        existing = intent_state.read_response(
            self.project_root,
            intent_id,
            state_dir=self._state_dir,
        )
        if existing is not None:
            value = existing.get("value")
            # Per spec §3, the consumed response is cleared by the
            # caller's success branch. The consumed-intent log
            # (re-entry idempotency) survives — that is the contract
            # of ``clear_intent_files(also_log=False)``.
            intent_state.clear_intent_files(
                self.project_root, state_dir=self._state_dir
            )
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
        )
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
    ) -> dict[str, Any]:
        """Assemble the canonical pending payload.

        Shape matches ``docs/schemas/intent-protocol.md`` and what
        ``engine.ui.question._build_pending`` emits in the native path.
        Keys are kebab-case on the wire by design — pre-existing host
        clients (and ``intent_state._check_schema_version``) already
        consume that shape.

        The adapter has no access to a CLI command context the way
        ``question._command_context`` does (this is a library facade,
        not a CLI entrypoint). We surface ``("host-adapter", [])`` so
        the field is present and machine-parseable; race detection only
        needs a stable ``intent-id`` and ``created-at``, not the
        command shape.
        """
        return {
            "schema-version": _SCHEMA_VERSION,
            "intent-id": intent_id,
            "command": "host-adapter",
            "command-args": [],
            "kind": kind.value,
            "question": question,
            "options": dict(options) if options else {},
            "default": default,
            "allow-pause": allow_pause,
            "created-at": _now_iso(),
            "pid": os.getpid(),
            "checkpoint-path": None,
        }
