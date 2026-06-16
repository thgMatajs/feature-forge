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
