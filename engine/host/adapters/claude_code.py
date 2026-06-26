"""ClaudeCodeAdapter — native CC host channel via stdout intent marker.

Spec: ``docs/superpowers/specs/2026-06-16-v1-3-pilot-ready-design.md`` §4
(Claude Code sequence).

Why a separate adapter (vs. ``IntentFileAdapter``)
==================================================

Under Claude Code (``CLAUDECODE=1``), the harness is the orchestrator —
it owns the user-facing UI surface (``AskUserQuestion`` etc.) and is
expected to consume forge's intents inline rather than poll a pending
file. The CC channel is therefore:

1. Forge emits a single-line, self-closing XML marker on ``stdout`` —
   ``<FORGE_INTENT kind="..." intent-id="..." question="..." .../>``.
2. Forge raises ``PausedForInputError`` so the engine bubbles up exit 2.
3. CC reads the marker (line-oriented stdout consumer), dispatches
   ``AskUserQuestion`` natively, captures the answer.
4. CC writes ``forge-response.json`` to ``.claude/forge/state/`` per the
   DRIFT-1 file protocol so re-entry works without CC needing to keep
   any forge-internal in-memory state.
5. CC re-invokes ``forge`` with the same args. The adapter's
   first action is ``intent_state.read_response(...)``; finding the
   cached entry returns an ``AskResult`` immediately. Idempotent by
   construction — same ``stable_intent_id`` chokepoint as
   ``IntentFileAdapter``.

The key difference from the fallback adapter: **no pending.json is
written on this channel**. The stdout marker IS the pending notification.
Writing a pending file would be dead weight: CC would never read it (it
already saw the marker), and on re-entry forge clears the file anyway.
Skipping the write also keeps the CC path tidy — no temp file fsync
overhead, no race window between marker emit and pending write.

Re-entry consume reuses the exact same ``intent_state.read_response`` +
``clear_intent_files`` dance the file adapter performs. That is by
design — the response side of the protocol is identical regardless of
how the pending was announced (stdout marker vs pending file).

Task 0.7a (parity-with-question hardening): adapter now accepts
``min_selected`` / ``validator_hint`` / ``paths_detail`` extras and
resolves ``(command, command_args)`` via ``_command_context()``. The
stdout marker also surfaces those optional fields as XML attributes
when present — useful signal for the CC harness when dispatching
``AskUserQuestion`` (e.g. ``validator-hint="email"`` lets the harness
attach client-side validation). Attributes are omitted when ``None``
so existing CC parsers that key on attribute presence keep working.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from xml.sax.saxutils import quoteattr

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


class ClaudeCodeAdapter(HostAdapter):
    """Native Claude Code host adapter — stdout marker + intent-log re-entry.

    Construction is cheap; the adapter holds only ``project_root`` and a
    cached ``state_dir`` so every method passes the same anchor through
    to ``intent_state`` for response lookup / clear.
    """

    name = HostName.CLAUDE_CODE

    def __init__(self, *, project_root: Path):
        self.project_root = Path(project_root)
        self._state_dir = forge_state_dir(self.project_root)

    # ------------------------------------------------------------------
    # ask / ask_text / ask_multi — stdout marker + re-entry consume
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
        return [str(value)]

    # ------------------------------------------------------------------
    # emit_progress / emit_warn — non-blocking channels
    # ------------------------------------------------------------------

    def emit_progress(self, *, step: str, total: int, current: int) -> None:
        # Non-blocking by design. CC has its own progress surface; forge
        # does not currently emit progress markers on the CC channel.
        # If/when a richer protocol is needed, this is where a
        # ``<FORGE_PROGRESS .../>`` marker would land — but writing to
        # stdout speculatively today would interleave with the intent
        # marker and confuse the line-oriented harness consumer.
        return None

    def emit_warn(self, *, message: str) -> None:
        # Non-blocking by design. Same rationale as ``emit_progress``;
        # CC surfaces forge warnings via its own UI, not via a side
        # channel from the engine.
        return None

    # ------------------------------------------------------------------
    # classify — intent-kind classify (pending file + stdout marker)
    # ------------------------------------------------------------------

    def classify(
        self,
        *,
        fragments: list[dict],
        schema: dict,
    ) -> list[dict] | None:
        """Classify rule fragments via CC's pending file + stdout marker.

        Because ``fragments`` can be a large payload, classify writes the
        full pending file (so the host can read the fragments from disk)
        AND emits a compact stdout marker (so CC's line-oriented consumer
        knows a pending is waiting). Re-entry is identical to the
        ``IntentFileAdapter`` path — same ``intent_state.read_response``
        chokepoint, same ``_SCHEMA_VERSION``.
        """
        from engine.host.adapters.intent_file import _SCHEMA_VERSION, _now_iso as _if_now_iso

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
            from engine.host.adapter import UserCancelledError as _UC, UserPausedError as _UP
            if existing.get("cancelled") is True:
                raise _UC(f"user cancelled (intent-id={intent_id})")
            if existing.get("paused") is True:
                raise _UP(f"user paused (intent-id={intent_id})")
            return existing.get("classification")
        # First entry: write the pending file (fragments are too large for
        # the marker alone) and emit a compact stdout marker so CC knows
        # to read the pending file.
        import os as _os
        from engine.ui import intent_state as _is
        intent = {
            "schema-version": _SCHEMA_VERSION,
            "kind": AskKind.CLASSIFY.value,
            "intent-id": intent_id,
            "command": command,
            "command-args": list(command_args),
            "fragments": fragments,
            "classification-schema": schema,
            "created-at": _if_now_iso(),
            "pid": _os.getpid(),
        }
        from engine.utils.paths import forge_state_dir as _fsd
        state_dir = _fsd(self.project_root)
        with _is.pending_lock(self.project_root, state_dir=state_dir):
            _is.detect_race(
                self.project_root,
                new_intent_id=intent_id,
                state_dir=state_dir,
            )
            _is.write_pending(intent, self.project_root, state_dir=state_dir)
        # Compact stdout marker — CC reads the pending file for fragments.
        self._emit_marker(
            intent_id=intent_id,
            kind=AskKind.CLASSIFY,
            question="classify-rules",
            options={},
            default=None,
            allow_pause=True,
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
        clean. See ``IntentFileAdapter._resolve_command_context`` for
        the canonical rationale; the two adapters share this helper
        shape so an eventual base-class refactor stays trivial.
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
        """Shared loop body — re-entry consume OR first-entry marker emit.

        The ``intent_id`` derivation matches ``IntentFileAdapter`` bit
        for bit so a CC session that started under the fallback (or
        vice-versa) still lines up via the consumed-intent log.

        Hash extras include ``min-selected`` / ``validator-hint``;
        ``paths-detail`` is added to the hash dict only when not None
        (MD-fix #11 parity with ``question._build_pending``).
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

        # Re-entry: response already waiting? CC writes
        # ``forge-response.json`` after dispatching AskUserQuestion;
        # ``read_response`` also consults the consumed-intent log so
        # multi-intent handlers re-enter safely.
        existing = intent_state.read_response(
            self.project_root,
            intent_id,
            state_dir=self._state_dir,
        )
        if existing is not None:
            # CR-001 / CR-003 — propagate pause/cancel intent as
            # exceptions instead of silently coercing to AskResult.
            # Same contract as ``IntentFileAdapter._ask_loop``; the CC
            # response side of DRIFT-1 is identical regardless of how
            # the pending was announced (stdout marker vs pending file).
            #
            # State is left in place on these paths: cleanup is
            # ``engine.cli`` finally's job (CR-002 forensic preservation).
            if existing.get("cancelled") is True:
                raise UserCancelledError(
                    f"user cancelled (intent-id={intent_id})"
                )
            if existing.get("paused") is True:
                raise UserPausedError(
                    f"user paused (intent-id={intent_id})"
                )
            # Happy path: return value, DO NOT auto-clear state. The
            # caller (cli.py finally) handles cleanup AFTER
            # post-delegate validation accepts the value — see CR-002
            # rationale in the fallback adapter sibling.
            value = existing.get("value")
            return AskResult(value=value, from_default=False, paused=False)

        # First entry: emit the stdout marker (CC's pending channel),
        # raise the paused sentinel for the engine to bubble up as
        # exit code 2.
        self._emit_marker(
            intent_id=intent_id,
            kind=kind,
            question=question,
            options=options,
            default=default,
            allow_pause=allow_pause,
            min_selected=min_selected,
            validator_hint=validator_hint,
            paths_detail=paths_detail,
        )
        raise PausedForInputError(
            f"forge paused awaiting host response (intent-id={intent_id})"
        )

    def _emit_marker(
        self,
        *,
        intent_id: str,
        kind: AskKind,
        question: str,
        options: dict,
        default: str | None,
        allow_pause: bool,
        min_selected: int | None = None,
        validator_hint: str | None = None,
        paths_detail: list[dict[str, str]] | None = None,
    ) -> None:
        """Write the single-line ``<FORGE_INTENT .../>`` marker to stdout.

        Attribute encoding rules:

        - ``options`` is JSON-encoded (``json.dumps`` with default
          settings) then XML-attribute-quoted. JSON-in-XML keeps nested
          structure parseable on the consumer side with two stdlib
          parsers (``ElementTree`` for the outer marker, ``json.loads``
          for the inner payload). No bespoke escape rules required.
        - ``default=None`` becomes ``default="null"`` (literal string).
          The CC consumer treats ``"null"`` as "no default supplied";
          choosing the JSON-literal form keeps the attribute always
          present and unambiguously stringy, which is friendlier to a
          line-oriented attribute parser than an empty-string distinction.
        - All other attribute values go through ``xml.sax.saxutils.quoteattr``
          which handles ``<``, ``>``, ``&``, and quote escaping
          consistently. The result is well-formed XML — verifiable by
          round-tripping the marker through ``ElementTree.fromstring``.

        Task 0.7a optional attributes:
        - ``validator-hint`` / ``min-selected`` / ``paths-detail`` are
          emitted ONLY when not None — mirroring the conditional
          payload fields in ``question._build_pending`` and
          ``IntentFileAdapter._build_pending``. Hosts that key on
          attribute presence (``"validator-hint" in attrib``) continue
          to work; ``paths-detail`` is JSON-encoded (list of dicts) for
          the same reason ``options`` is — nested structure stays
          parseable with stdlib alone.

        ``sys.stdout.write`` + ``flush`` (not ``print``) is deliberate:
        ``print``'s newline handling and the global ``sys.stdout.softspace``
        legacy can interact badly with harness consumers that read a
        single line and expect exact byte semantics. Explicit ``\\n``
        appended once keeps the output a clean single line.
        """
        attrs: dict[str, str] = {
            "kind": kind.value,
            "intent-id": intent_id,
            "question": question,
            "options": json.dumps(options or {}, ensure_ascii=False),
            # ``default=None`` → literal "null". See docstring.
            "default": "null" if default is None else default,
            "allow-pause": "true" if allow_pause else "false",
        }
        # Optional Task 0.7a attributes — present only when set, matching
        # the conditional payload behaviour of question._build_pending.
        if validator_hint is not None:
            attrs["validator-hint"] = validator_hint
        if min_selected is not None:
            attrs["min-selected"] = str(min_selected)
        if paths_detail is not None:
            attrs["paths-detail"] = json.dumps(paths_detail, ensure_ascii=False)
        # Build attribute string with xml.sax.saxutils.quoteattr so every
        # value is wrapped in matching quotes with embedded specials
        # escaped (&amp; &lt; &gt; &quot; &apos;).
        attr_str = " ".join(f"{k}={quoteattr(v)}" for k, v in attrs.items())
        marker = f"<FORGE_INTENT {attr_str} />\n"
        sys.stdout.write(marker)
        sys.stdout.flush()
