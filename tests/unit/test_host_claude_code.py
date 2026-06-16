"""Unit tests for ``engine.host.adapters.claude_code.ClaudeCodeAdapter``.

Contract verified (spec §4 — Claude Code sequence):

- ``ask()`` first-entry path emits an XML-style ``<FORGE_INTENT .../>``
  self-closing marker on ``sys.stdout`` and raises ``PausedForInputError``.
  The stdout marker IS the pending notification on the CC channel —
  there is NO ``forge-pending.json`` write here. Spec §4 contracts CC
  consumes the marker, dispatches ``AskUserQuestion`` natively, and
  writes ``forge-response.json`` directly.
- Re-entry path (matching response already on disk in the consumed
  log OR response file) consumes the response and returns an
  ``AskResult`` without raising — same idempotency invariant as
  ``IntentFileAdapter`` because the same ``stable_intent_id`` /
  ``intent_state.read_response`` chokepoints are reused.
- ``emit_warn`` and ``emit_progress`` are non-blocking (no exception,
  no pending file written).
- Marker attributes are XML-safe (special chars escaped) — the marker
  must parse as well-formed XML so the CC harness can consume it with
  a standard XML reader.
"""
from __future__ import annotations

from xml.etree import ElementTree as ET

import pytest

from engine.host.adapter import AskKind, AskResult, PausedForInputError
from engine.host.adapters.claude_code import ClaudeCodeAdapter


def test_ask_emits_stdout_marker_and_pauses(tmp_path, capsys):
    adapter = ClaudeCodeAdapter(project_root=tmp_path)
    with pytest.raises(PausedForInputError):
        adapter.ask(
            kind=AskKind.ASK,
            question="Tipo da feature?",
            options={"product": "Product feature", "bugfix": "Bug fix"},
            default=None,
            allow_pause=True,
        )
    captured = capsys.readouterr()
    out = captured.out
    assert "<FORGE_INTENT" in out
    assert 'kind="ask"' in out
    assert 'question="Tipo da feature?"' in out
    # Must end with self-closing /> form
    assert "/>" in out

    # CC adapter MUST NOT write pending.json — stdout marker is the channel
    pending = tmp_path / ".claude" / "forge" / "state" / "forge-pending.json"
    assert not pending.exists()


def test_ask_consumes_cached_response_on_reentry(tmp_path):
    """Pre-populate response.json (simulating CC having asked user). Re-entry returns AskResult."""
    from engine.ui import intent_state
    from engine.ui.question import stable_intent_id
    from engine.utils.paths import forge_state_dir

    state = forge_state_dir(tmp_path)
    state.mkdir(parents=True)

    kind = AskKind.ASK
    question = "Tipo da feature?"
    options = {"product": "Product feature", "bugfix": "Bug fix"}
    intent_id = stable_intent_id(
        kind.value,
        question,
        options,
        extra={"default": None, "min-selected": None, "validator-hint": None},
        command="host-adapter",
        command_args=[],
    )

    # Simulate CC harness writing the matching response.
    intent_state.write_response(
        tmp_path,
        {
            "schema-version": 1,
            "intent-id": intent_id,
            "value": "product",
        },
        state_dir=state,
    )
    # Reset log cache so the freshly-written response is visible.
    intent_state._reset_log_cache()

    adapter = ClaudeCodeAdapter(project_root=tmp_path)
    result = adapter.ask(
        kind=kind,
        question=question,
        options=options,
        default=None,
        allow_pause=True,
    )
    assert isinstance(result, AskResult)
    assert result.value == "product"
    assert result.paused is False


def test_emit_progress_and_warn_non_blocking(tmp_path):
    adapter = ClaudeCodeAdapter(project_root=tmp_path)
    adapter.emit_progress(step="planning", total=10, current=3)
    adapter.emit_warn(message="heads up")
    pending = tmp_path / ".claude" / "forge" / "state" / "forge-pending.json"
    assert not pending.exists()


def test_marker_xml_escapes_special_chars(tmp_path, capsys):
    """Question containing < > & " must produce a well-formed XML marker.

    Validation via stdlib XML parse: the marker must round-trip through
    ``ElementTree.fromstring``, which is stricter than any ad-hoc
    substring check — guarantees no unescaped ``<``/``&``/``"`` leak
    into attribute values and break the CC consumer.
    """
    adapter = ClaudeCodeAdapter(project_root=tmp_path)
    tricky = 'Use "X" & validate <input>?'
    with pytest.raises(PausedForInputError):
        adapter.ask(
            kind=AskKind.ASK_TEXT,
            question=tricky,
            options={},
            default=None,
            allow_pause=True,
        )
    out = capsys.readouterr().out
    assert "<FORGE_INTENT" in out

    # Extract just the marker line (last non-blank line of stdout).
    marker_line = next(
        line for line in reversed(out.splitlines()) if line.strip().startswith("<FORGE_INTENT")
    )
    # Must parse as well-formed XML.
    elem = ET.fromstring(marker_line)
    assert elem.tag == "FORGE_INTENT"
    assert elem.attrib["kind"] == "ask_text"
    # Round-trip preserves the original (unescaped) value in attrib dict.
    assert elem.attrib["question"] == tricky
