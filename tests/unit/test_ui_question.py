"""Unit tests — engine.ui.question (legacy stdin path, mostly migrated).

Pre DRIFT-1 W2 these tests drove the interactive prompt API by stubbing
``sys.stdin``. The W2 refactor moved stdin handling to
``engine.ui.tty_bridge`` (W3) — the engine itself now emits intent files
and never reads stdin (SPEC §1).

The 11 stdin-based tests below are skipped with a reason pointing at
their successor module. ``test_ui_question_intent.py`` covers each one's
semantics on the new protocol side (matching response → returned value,
pause token via response → ``PromptAbortedError``, etc.). When
``test_tty_bridge.py`` lands in W3 it will cover the stdin half of the
loop.

Two checks survive untouched — they exercise validation that fires
before any input is read (and therefore before any stdin / intent
emission happens):

- ``test_ask_empty_options_rejected`` — empty options → ``ValueError``
- ``test_ask_three_paths_requires_three`` — wrong arity → ``ValueError``

These are still useful regression guards.
"""

from __future__ import annotations

import io
import sys

import pytest

from engine.ui import question

_LEGACY_SKIP_REASON = (
    "legacy stdin path migrated to tty_bridge — see tests/unit/test_ui_question_intent.py "
    "for the intent-protocol equivalent and (W3) tests/unit/test_ui_tty_bridge.py for the "
    "stdin half of the loop."
)


def _patch_stdin(monkeypatch, lines: list[str]) -> None:
    payload = "\n".join(lines) + "\n"
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))


@pytest.mark.skip(reason=_LEGACY_SKIP_REASON)
def test_ask_returns_matched_key(monkeypatch, capsys):
    _patch_stdin(monkeypatch, ["a"])
    answer = question.ask("Pick:", {"a": "Apple", "b": "Banana"})
    assert answer == "a"


@pytest.mark.skip(reason=_LEGACY_SKIP_REASON)
def test_ask_uses_default_on_empty(monkeypatch, capsys):
    _patch_stdin(monkeypatch, [""])
    answer = question.ask("Pick:", {"a": "Apple", "b": "Banana"}, default="b")
    assert answer == "b"


@pytest.mark.skip(reason=_LEGACY_SKIP_REASON)
def test_ask_reprompts_on_invalid_then_accepts(monkeypatch, capsys):
    _patch_stdin(monkeypatch, ["nope", "a"])
    answer = question.ask("Pick:", {"a": "Apple"})
    assert answer == "a"


@pytest.mark.skip(reason=_LEGACY_SKIP_REASON)
def test_ask_pause_token_raises(monkeypatch, capsys):
    _patch_stdin(monkeypatch, ["para"])
    with pytest.raises(question.PromptAbortedError):
        question.ask("Pick:", {"a": "Apple"})


def test_ask_empty_options_rejected():
    """Survives the migration — fires before any input is read."""
    with pytest.raises(ValueError):
        question.ask("Pick:", {})


@pytest.mark.skip(reason=_LEGACY_SKIP_REASON)
def test_ask_multi_returns_in_options_order(monkeypatch, capsys):
    _patch_stdin(monkeypatch, ["c,a"])
    picked = question.ask_multi("Pick many:", {"a": "A", "b": "B", "c": "C"})
    # Should preserve the insertion order of options, not the user's input.
    assert picked == ["a", "c"]


@pytest.mark.skip(reason=_LEGACY_SKIP_REASON)
def test_ask_multi_min_selected_enforced(monkeypatch, capsys):
    _patch_stdin(monkeypatch, ["", "a,b"])
    picked = question.ask_multi("Pick:", {"a": "A", "b": "B"}, min_selected=1)
    assert picked == ["a", "b"]


@pytest.mark.skip(reason=_LEGACY_SKIP_REASON)
def test_ask_text_validator_rejects_then_accepts(monkeypatch, capsys):
    _patch_stdin(monkeypatch, ["bad", "good"])
    answer = question.ask_text(
        "Type:",
        validator=lambda s: s == "good",
        validator_hint="must be 'good'",
    )
    assert answer == "good"


@pytest.mark.skip(reason=_LEGACY_SKIP_REASON)
def test_ask_text_default(monkeypatch, capsys):
    _patch_stdin(monkeypatch, [""])
    answer = question.ask_text("Slug:", default="my-slug")
    assert answer == "my-slug"


def test_ask_three_paths_requires_three(monkeypatch, capsys):
    """Survives the migration — fires before any input is read."""
    with pytest.raises(ValueError):
        question.ask_three_paths(
            "gate",
            paths=[{"label": "A", "motive": ""}, {"label": "B", "motive": ""}],
        )


@pytest.mark.skip(reason=_LEGACY_SKIP_REASON)
def test_ask_three_paths_returns_choice(monkeypatch, capsys):
    _patch_stdin(monkeypatch, ["b"])
    answer = question.ask_three_paths(
        "gate",
        paths=[
            {"label": "First", "motive": "first motive"},
            {"label": "Second", "motive": "second motive"},
            {"label": "Third", "motive": "third motive"},
        ],
    )
    assert answer == "b"


@pytest.mark.skip(reason=_LEGACY_SKIP_REASON)
def test_confirm_yes(monkeypatch, capsys):
    _patch_stdin(monkeypatch, ["s"])
    assert question.confirm("ok?") is True


@pytest.mark.skip(reason=_LEGACY_SKIP_REASON)
def test_confirm_no_default(monkeypatch, capsys):
    _patch_stdin(monkeypatch, [""])
    assert question.confirm("ok?", default=False) is False
