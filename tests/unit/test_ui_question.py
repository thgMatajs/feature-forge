"""Unit tests — engine.ui.question.

Drives the interactive prompt API by stubbing stdin. Validates default
fallback, validator hint, pause-token detection, and ask_three_paths arity.
"""

from __future__ import annotations

import io
import sys

import pytest

from engine.ui import question


def _patch_stdin(monkeypatch, lines: list[str]) -> None:
    payload = "\n".join(lines) + "\n"
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))


def test_ask_returns_matched_key(monkeypatch, capsys):
    _patch_stdin(monkeypatch, ["a"])
    answer = question.ask("Pick:", {"a": "Apple", "b": "Banana"})
    assert answer == "a"


def test_ask_uses_default_on_empty(monkeypatch, capsys):
    _patch_stdin(monkeypatch, [""])
    answer = question.ask("Pick:", {"a": "Apple", "b": "Banana"}, default="b")
    assert answer == "b"


def test_ask_reprompts_on_invalid_then_accepts(monkeypatch, capsys):
    _patch_stdin(monkeypatch, ["nope", "a"])
    answer = question.ask("Pick:", {"a": "Apple"})
    assert answer == "a"


def test_ask_pause_token_raises(monkeypatch, capsys):
    _patch_stdin(monkeypatch, ["para"])
    with pytest.raises(question.PromptAbortedError):
        question.ask("Pick:", {"a": "Apple"})


def test_ask_empty_options_rejected():
    with pytest.raises(ValueError):
        question.ask("Pick:", {})


def test_ask_multi_returns_in_options_order(monkeypatch, capsys):
    _patch_stdin(monkeypatch, ["c,a"])
    picked = question.ask_multi("Pick many:", {"a": "A", "b": "B", "c": "C"})
    # Should preserve the insertion order of options, not the user's input.
    assert picked == ["a", "c"]


def test_ask_multi_min_selected_enforced(monkeypatch, capsys):
    _patch_stdin(monkeypatch, ["", "a,b"])
    picked = question.ask_multi("Pick:", {"a": "A", "b": "B"}, min_selected=1)
    assert picked == ["a", "b"]


def test_ask_text_validator_rejects_then_accepts(monkeypatch, capsys):
    _patch_stdin(monkeypatch, ["bad", "good"])
    answer = question.ask_text(
        "Type:",
        validator=lambda s: s == "good",
        validator_hint="must be 'good'",
    )
    assert answer == "good"


def test_ask_text_default(monkeypatch, capsys):
    _patch_stdin(monkeypatch, [""])
    answer = question.ask_text("Slug:", default="my-slug")
    assert answer == "my-slug"


def test_ask_three_paths_requires_three(monkeypatch, capsys):
    with pytest.raises(ValueError):
        question.ask_three_paths(
            "gate",
            paths=[{"label": "A", "motive": ""}, {"label": "B", "motive": ""}],
        )


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


def test_confirm_yes(monkeypatch, capsys):
    _patch_stdin(monkeypatch, ["s"])
    assert question.confirm("ok?") is True


def test_confirm_no_default(monkeypatch, capsys):
    _patch_stdin(monkeypatch, [""])
    assert question.confirm("ok?", default=False) is False
