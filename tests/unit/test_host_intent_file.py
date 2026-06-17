"""Unit tests for ``engine.host.adapters.intent_file.IntentFileAdapter``.

Contract verified:

- ``ask()`` first-entry path emits pending JSON into the v1.3
  sub-namespace ``.claude/forge/state/forge-pending.json`` and raises
  ``PausedForInputError``.
- The legacy ``.claude/state/forge-pending.json`` path is NOT touched
  (proving Task 0.5 redirection works).
- Re-entry path (matching response on disk) consumes the response and
  returns an ``AskResult`` without raising.
- ``emit_warn`` and ``emit_progress`` are non-blocking (no exception,
  no pending file written).

Schema invariant: the on-disk payload uses kebab-case keys
(``schema-version``, ``intent-id``, ``created-at``, ``command-args``,
etc.) per ``docs/schemas/intent-protocol.md`` and matches the format
``engine.ui.question._build_pending`` produces.
"""
from __future__ import annotations

import json

import pytest

from engine.host.adapter import (
    AskKind,
    AskResult,
    PausedForInputError,
)
from engine.host.adapters.intent_file import IntentFileAdapter
from engine.ui import intent_state
from engine.utils.paths import forge_state_dir


def test_ask_emits_pending_in_forge_state_dir_and_raises_paused(tmp_path):
    """First-entry path: no response on disk → emit pending, raise paused."""
    adapter = IntentFileAdapter(project_root=tmp_path)
    with pytest.raises(PausedForInputError):
        adapter.ask(
            kind=AskKind.ASK,
            question="Tipo da feature?",
            options={"product": "Product feature", "bugfix": "Bug fix"},
            default=None,
            allow_pause=True,
        )

    pending = tmp_path / ".claude" / "forge" / "state" / "forge-pending.json"
    assert pending.exists(), (
        "pending.json must land in .claude/forge/state/ (v1.3 sub-namespace), "
        "not .claude/state/ (legacy DRIFT-1 location)."
    )
    data = json.loads(pending.read_text())
    # Canonical kebab-case schema per docs/schemas/intent-protocol.md
    assert data["kind"] == "ask"
    assert data["question"] == "Tipo da feature?"
    assert data["options"] == {"product": "Product feature", "bugfix": "Bug fix"}
    assert data["schema-version"] == 1
    assert "intent-id" in data and isinstance(data["intent-id"], str)
    assert "created-at" in data
    assert data["allow-pause"] is True
    assert data["default"] is None

    # The legacy location must NOT be written — proves Task 0.5
    # redirection is fully effective.
    legacy = tmp_path / ".claude" / "state" / "forge-pending.json"
    assert not legacy.exists()


def test_ask_consumes_matching_response_and_returns_value(tmp_path):
    """Re-entry: pending emitted, host wrote response, second ask returns it."""
    adapter = IntentFileAdapter(project_root=tmp_path)

    # First call: emit pending (catches the PausedForInputError sentinel)
    try:
        adapter.ask(
            kind=AskKind.ASK,
            question="Q?",
            options={"a": "A", "b": "B"},
            default=None,
            allow_pause=True,
        )
    except PausedForInputError:
        pass

    # Discover the intent-id the adapter produced (we don't reach into
    # private helpers — we read it off the pending file the same way a
    # real host would).
    state = forge_state_dir(tmp_path)
    pending_payload = json.loads((state / "forge-pending.json").read_text())
    intent_id = pending_payload["intent-id"]
    schema_version = pending_payload["schema-version"]

    # Reset the intent-log cache so the fresh response is observed.
    # Required because tests reuse paths and the cache is module-level.
    intent_state._reset_log_cache()

    # Simulate the host writing a matching response into the same
    # sub-namespace the adapter watches.
    intent_state.write_response(
        tmp_path,
        {
            "schema-version": schema_version,
            "intent-id": intent_id,
            "value": "a",
        },
        state_dir=state,
    )

    # Second call (re-entry): same question, same options → SAME
    # intent-id → response is consumed and returned as AskResult.
    result = adapter.ask(
        kind=AskKind.ASK,
        question="Q?",
        options={"a": "A", "b": "B"},
        default=None,
        allow_pause=True,
    )
    assert isinstance(result, AskResult)
    assert result.value == "a"
    assert result.paused is False


def test_emit_warn_does_not_raise_and_does_not_write_pending(tmp_path):
    """Non-blocking emit_warn — must NOT raise nor emit a pending file."""
    adapter = IntentFileAdapter(project_root=tmp_path)
    adapter.emit_warn(message="heads up")
    pending = tmp_path / ".claude" / "forge" / "state" / "forge-pending.json"
    assert not pending.exists()


def test_emit_progress_does_not_raise(tmp_path):
    """Non-blocking emit_progress — no exception, no side effect required."""
    adapter = IntentFileAdapter(project_root=tmp_path)
    adapter.emit_progress(step="planning", total=10, current=3)
    # Success criterion: no exception. The intent-file fallback has no
    # progress channel by design.


# ----------------------------------------------------------------------
# Cross-AI review HIGH — ask_three_paths + confirm on the file channel
# ----------------------------------------------------------------------


def test_three_paths_emits_pending_with_paths_detail(tmp_path):
    """``ASK_THREE_PATHS`` first-entry writes a pending carrying the
    canonical 3-caminhos shape (options a/b/c + paths-detail).
    """
    adapter = IntentFileAdapter(project_root=tmp_path)
    paths_detail = [
        {"key": "a", "label": "Refatorar", "motive": "reduz complexidade"},
        {"key": "b", "label": "Reverter", "motive": "desfaz o commit"},
        {"key": "c", "label": "Override-justify", "motive": "documenta no commit"},
    ]
    with pytest.raises(PausedForInputError):
        adapter.ask(
            kind=AskKind.ASK_THREE_PATHS,
            question="Qual caminho para 'cc-gate'?",
            options={"a": "Refatorar", "b": "Reverter", "c": "Override-justify"},
            default=None,
            allow_pause=True,
            paths_detail=paths_detail,
        )
    pending = json.loads(
        (forge_state_dir(tmp_path) / "forge-pending.json").read_text()
    )
    assert pending["kind"] == "ask_three_paths"
    assert pending["options"] == {
        "a": "Refatorar",
        "b": "Reverter",
        "c": "Override-justify",
    }
    assert pending["paths-detail"] == paths_detail


def test_three_paths_consumes_choice_key_on_reentry(tmp_path):
    """Re-entry returns the picked key the host wrote."""
    adapter = IntentFileAdapter(project_root=tmp_path)
    paths_detail = [
        {"key": "a", "label": "A", "motive": "ma"},
        {"key": "b", "label": "B", "motive": "mb"},
        {"key": "c", "label": "C", "motive": "mc"},
    ]
    try:
        adapter.ask(
            kind=AskKind.ASK_THREE_PATHS,
            question="Qual caminho?",
            options={"a": "A", "b": "B", "c": "C"},
            default=None,
            allow_pause=True,
            paths_detail=paths_detail,
        )
    except PausedForInputError:
        pass
    state = forge_state_dir(tmp_path)
    intent_id = json.loads((state / "forge-pending.json").read_text())["intent-id"]
    intent_state._reset_log_cache()
    intent_state.write_response(
        tmp_path,
        {"schema-version": 1, "intent-id": intent_id, "value": "c"},
        state_dir=state,
    )
    result = adapter.ask(
        kind=AskKind.ASK_THREE_PATHS,
        question="Qual caminho?",
        options={"a": "A", "b": "B", "c": "C"},
        default=None,
        allow_pause=True,
        paths_detail=paths_detail,
    )
    assert result.value == "c"


def test_confirm_emits_pending_with_confirm_kind(tmp_path):
    """``CONFIRM`` first-entry writes a pending with s/n options + default."""
    adapter = IntentFileAdapter(project_root=tmp_path)
    with pytest.raises(PausedForInputError):
        adapter.ask(
            kind=AskKind.CONFIRM,
            question="Aplicar?",
            options={"s": "sim", "n": "não"},
            default="n",
            allow_pause=True,
        )
    pending = json.loads(
        (forge_state_dir(tmp_path) / "forge-pending.json").read_text()
    )
    assert pending["kind"] == "confirm"
    assert pending["options"] == {"s": "sim", "n": "não"}
    assert pending["default"] == "n"


def test_confirm_consumes_bool_response_on_reentry(tmp_path):
    adapter = IntentFileAdapter(project_root=tmp_path)
    try:
        adapter.ask(
            kind=AskKind.CONFIRM,
            question="Aplicar?",
            options={"s": "sim", "n": "não"},
            default="n",
            allow_pause=True,
        )
    except PausedForInputError:
        pass
    state = forge_state_dir(tmp_path)
    intent_id = json.loads((state / "forge-pending.json").read_text())["intent-id"]
    intent_state._reset_log_cache()
    intent_state.write_response(
        tmp_path,
        {"schema-version": 1, "intent-id": intent_id, "value": True},
        state_dir=state,
    )
    result = adapter.ask(
        kind=AskKind.CONFIRM,
        question="Aplicar?",
        options={"s": "sim", "n": "não"},
        default="n",
        allow_pause=True,
    )
    assert result.value is True


# ----------------------------------------------------------------------
# Task 0.7a — parity with question._build_pending
# ----------------------------------------------------------------------


def test_ask_text_validator_hint_changes_intent_id(tmp_path):
    """HI-002 / MD-001 parity: distinct ``validator_hint`` → distinct intent-id.

    Two ``ask_text`` calls with the SAME prompt but DIFFERENT
    ``validator_hint`` MUST produce different intent-ids, otherwise a
    stale response intended for validator A could be consumed by a
    call expecting validator B. This mirrors the parity invariant
    enforced inside ``engine.ui.question._build_pending``.
    """
    adapter = IntentFileAdapter(project_root=tmp_path)
    state = forge_state_dir(tmp_path)

    # First call — validator_hint="email"
    try:
        adapter.ask_text(prompt="Enter:", default=None, validator_hint="email")
    except PausedForInputError:
        pass
    pending_a = json.loads((state / "forge-pending.json").read_text())
    id_a = pending_a["intent-id"]
    assert pending_a["validator-hint"] == "email"

    # Clear the pending file + log cache so the next call starts fresh.
    (state / "forge-pending.json").unlink()
    intent_state._reset_log_cache()

    # Second call — same prompt, different validator_hint.
    try:
        adapter.ask_text(prompt="Enter:", default=None, validator_hint="phone")
    except PausedForInputError:
        pass
    pending_b = json.loads((state / "forge-pending.json").read_text())
    id_b = pending_b["intent-id"]
    assert pending_b["validator-hint"] == "phone"

    assert id_a != id_b, (
        "validator_hint must enter the intent-id hash (MD-001 parity); "
        "same prompt with different hints produced identical ids."
    )


def test_ask_pending_uses_command_context(tmp_path):
    """HI-002 invariant: ``pending["command"]`` reflects ``_command_context``, NOT 'host-adapter'.

    Pre-0.7a the adapter hardcoded ``"host-adapter"`` + ``[]`` for the
    command tuple. When question.py delegates to the adapter (Task 0.7b),
    that hardcode would regress HI-002 — pending JSON would advertise
    ``"host-adapter"`` instead of the actual ``cli.main`` argv. This
    test pins the fix: setting the contextvar must propagate into the
    pending payload bit-a-bit.
    """
    from engine.ui.question import _cli_command_context

    token = _cli_command_context.set(("plan", ["IN-42100"]))
    try:
        adapter = IntentFileAdapter(project_root=tmp_path)
        with pytest.raises(PausedForInputError):
            adapter.ask(
                kind=AskKind.ASK,
                question="Q?",
                options={"a": "A"},
                default=None,
                allow_pause=True,
            )
        pending = json.loads(
            (forge_state_dir(tmp_path) / "forge-pending.json").read_text()
        )
        assert pending["command"] == "plan"
        assert pending["command-args"] == ["IN-42100"]
    finally:
        _cli_command_context.reset(token)


def test_pending_omits_optional_fields_when_none(tmp_path):
    """Wire-shape parity: ``min-selected`` / ``validator-hint`` / ``paths-detail``
    appear in the pending payload ONLY when supplied (not None).

    Mirrors ``question._build_pending`` lines 367-372 — including those
    keys with ``None`` values would diverge from the native path and
    break hosts that key on ``"validator-hint" in payload``.
    """
    adapter = IntentFileAdapter(project_root=tmp_path)
    with pytest.raises(PausedForInputError):
        adapter.ask(
            kind=AskKind.ASK,
            question="Q?",
            options={"a": "A"},
            default=None,
            allow_pause=True,
        )
    pending = json.loads(
        (forge_state_dir(tmp_path) / "forge-pending.json").read_text()
    )
    assert "validator-hint" not in pending
    assert "min-selected" not in pending
    assert "paths-detail" not in pending


def test_pending_includes_optional_fields_when_supplied(tmp_path):
    """Inverse of the omit-when-None case: when callers pass extras,
    the payload surfaces them on the wire."""
    adapter = IntentFileAdapter(project_root=tmp_path)
    paths_detail = [{"path": "src/foo.py", "blast": "high"}]
    with pytest.raises(PausedForInputError):
        adapter.ask(
            kind=AskKind.ASK_MULTI,
            question="Pick files?",
            options={"a": "A"},
            default=None,
            allow_pause=True,
            min_selected=2,
            validator_hint="email",
            paths_detail=paths_detail,
        )
    pending = json.loads(
        (forge_state_dir(tmp_path) / "forge-pending.json").read_text()
    )
    assert pending["validator-hint"] == "email"
    assert pending["min-selected"] == 2
    assert pending["paths-detail"] == paths_detail


# ----------------------------------------------------------------------
# Task 0.7c — pause/cancel propagation + CR-002 state preservation
# ----------------------------------------------------------------------


def test_ask_response_paused_raises_user_paused(tmp_path):
    """Response with ``paused=true`` triggers ``UserPausedError``, NOT ``AskResult``.

    CR-001: pre-0.7c the adapter swallowed ``response.paused=true`` and
    returned ``AskResult(value=None, paused=False)``, hiding user intent.
    The new contract surfaces pause as an exception so question.py
    post-delegate can map it to exit code 2.
    """
    from engine.host.adapter import UserPausedError

    state = forge_state_dir(tmp_path)
    state.mkdir(parents=True, exist_ok=True)
    adapter = IntentFileAdapter(project_root=tmp_path)
    # Emit pending so an ``intent-id`` is materialised.
    try:
        adapter.ask(
            kind=AskKind.ASK,
            question="Q?",
            options={"a": "A"},
            default=None,
            allow_pause=True,
        )
    except PausedForInputError:
        pass
    intent_id = json.loads((state / "forge-pending.json").read_text())["intent-id"]
    intent_state.write_response(
        tmp_path,
        {"schema-version": 1, "intent-id": intent_id, "paused": True},
        state_dir=state,
    )
    intent_state._reset_log_cache()
    with pytest.raises(UserPausedError):
        adapter.ask(
            kind=AskKind.ASK,
            question="Q?",
            options={"a": "A"},
            default=None,
            allow_pause=True,
        )


def test_ask_response_cancelled_raises_user_cancelled(tmp_path):
    """Response with ``cancelled=true`` triggers ``UserCancelledError``.

    CR-003: same rationale as ``UserPausedError``, but for cancel —
    maps to exit code 130 (SIGINT parity) at the CLI boundary. Pre-0.7c
    this was indistinguishable from a malformed response.
    """
    from engine.host.adapter import UserCancelledError

    state = forge_state_dir(tmp_path)
    state.mkdir(parents=True, exist_ok=True)
    adapter = IntentFileAdapter(project_root=tmp_path)
    try:
        adapter.ask(
            kind=AskKind.ASK,
            question="Q?",
            options={"a": "A"},
            default=None,
            allow_pause=True,
        )
    except PausedForInputError:
        pass
    intent_id = json.loads((state / "forge-pending.json").read_text())["intent-id"]
    intent_state.write_response(
        tmp_path,
        {"schema-version": 1, "intent-id": intent_id, "cancelled": True},
        state_dir=state,
    )
    intent_state._reset_log_cache()
    with pytest.raises(UserCancelledError):
        adapter.ask(
            kind=AskKind.ASK,
            question="Q?",
            options={"a": "A"},
            default=None,
            allow_pause=True,
        )


def test_ask_consume_preserves_state_files_cr_002(tmp_path):
    """CR-002 — after happy-path consume, pending + response files remain on disk.

    State cleanup is the responsibility of ``engine.cli`` finally (or
    the caller), not the adapter. Auto-clearing here would prevent
    post-delegate validation in question.py from preserving forensic
    state when it rejects a malformed value (e.g. ``value not in options``).

    Test ``test_invalid_response_preserves_state_files`` (question.py
    suite) enforces the same invariant end-to-end.
    """
    state = forge_state_dir(tmp_path)
    state.mkdir(parents=True, exist_ok=True)
    adapter = IntentFileAdapter(project_root=tmp_path)
    try:
        adapter.ask(
            kind=AskKind.ASK,
            question="Q?",
            options={"a": "A"},
            default=None,
            allow_pause=True,
        )
    except PausedForInputError:
        pass
    intent_id = json.loads((state / "forge-pending.json").read_text())["intent-id"]
    intent_state.write_response(
        tmp_path,
        {"schema-version": 1, "intent-id": intent_id, "value": "a"},
        state_dir=state,
    )
    intent_state._reset_log_cache()
    result = adapter.ask(
        kind=AskKind.ASK,
        question="Q?",
        options={"a": "A"},
        default=None,
        allow_pause=True,
    )
    assert result.value == "a"
    # CR-002: state preserved across consume for forensic / caller cleanup.
    assert (state / "forge-pending.json").exists(), "pending must survive consume"
    assert (state / "forge-response.json").exists(), "response must survive consume"
