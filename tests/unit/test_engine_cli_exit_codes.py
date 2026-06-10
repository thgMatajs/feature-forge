"""Exit-code mapping in ``engine.cli.main`` — DRIFT-1 W2.T2.

The top-level dispatcher must translate each control-flow shape into the
exit code contract from SPEC §8:

    0    success
    1    fatal error (handler raises something not caught here)
    2    paused — handler raised PausedForInputError, intent on disk
    130  user cancelled (KeyboardInterrupt — Decision 27)

The W2.T2 contract adds a new clause for code 2. The other paths are
asserted here too so any regression on them surfaces immediately.

Refs:
- docs/superpowers/specs/drift-1-intent-protocol.md §8
- docs/superpowers/plans/drift-1-intent-protocol.md W2.T2
"""

from __future__ import annotations

import sys

import pytest

import engine.cli as cli_module
from engine.cli import main
from engine.ui.question import (
    PausedForInputError,
    UserCancelledError,
    UserPausedError,
)


def _stub_handler(monkeypatch, handler):
    """Re-route ``cli._resolve`` so the test handler is dispatched for any cmd.

    Avoids the import-time machinery of real subcommand modules and keeps
    the test focused on cli.main's exception ladder.
    """
    monkeypatch.setattr(cli_module, "_resolve", lambda cmd: handler)


# --- exit 2 (the new clause) -----------------------------------------------


def test_paused_for_input_error_maps_to_exit_2(monkeypatch):
    """Handler raising PausedForInputError → main returns 2.

    The intent payload itself is irrelevant here; question.py is
    responsible for writing pending.json before raising. cli.main only
    needs to translate the sentinel to the exit code.
    """
    def handler(argv):
        raise PausedForInputError(intent={"kind": "ask", "question": "stub"})

    _stub_handler(monkeypatch, handler)
    assert main(["plan"]) == 2


def test_paused_for_input_error_does_not_print_traceback(monkeypatch, capsys):
    """exit 2 is a clean pause — no Python traceback should leak to stderr."""
    def handler(argv):
        raise PausedForInputError(intent={"kind": "ask"})

    _stub_handler(monkeypatch, handler)
    rc = main(["plan"])
    captured = capsys.readouterr()
    assert rc == 2
    assert "Traceback" not in captured.err
    assert "Traceback" not in captured.out


# --- exit 130 (Decision 27, regression) ------------------------------------


def test_keyboard_interrupt_maps_to_exit_130(monkeypatch):
    def handler(argv):
        raise KeyboardInterrupt

    _stub_handler(monkeypatch, handler)
    assert main(["plan"]) == 130


# --- exit 0 (regression) ---------------------------------------------------


def test_handler_returning_zero_maps_to_exit_0(monkeypatch):
    def handler(argv):
        return 0

    _stub_handler(monkeypatch, handler)
    assert main(["plan"]) == 0


def test_handler_returning_none_maps_to_exit_0(monkeypatch):
    """Legacy contract: handler returning None counts as success."""
    def handler(argv):
        return None

    _stub_handler(monkeypatch, handler)
    assert main(["plan"]) == 0


# --- exit 1 (regression — unhandled exception falls through) --------------


def test_unhandled_exception_propagates(monkeypatch):
    """RuntimeError other than PausedForInputError is NOT caught by main —
    callers see the traceback. This mirrors the pre-DRIFT-1 contract.
    """
    def handler(argv):
        raise RuntimeError("boom")

    _stub_handler(monkeypatch, handler)
    with pytest.raises(RuntimeError):
        main(["plan"])


# --- help / version smoke (regression on early-return paths) ---------------


def test_help_returns_zero(capsys):
    assert main(["--help"]) == 0
    captured = capsys.readouterr()
    assert "forge" in captured.out.lower()


def test_version_returns_zero(capsys):
    assert main(["--version"]) == 0


def test_empty_argv_returns_zero_with_help(capsys):
    assert main([]) == 0
    captured = capsys.readouterr()
    assert "forge" in captured.out.lower()


# --- exit 130 via UserCancelledError (CR-001 fix from W2 review) -----------


def test_cancelled_response_maps_to_exit_130(monkeypatch):
    """CR-001 fix — a host response with ``cancelled: true`` resolves
    inside ``question.py`` to ``UserCancelledError``; ``cli.main`` catches
    that sentinel and returns 130, parallel to ``KeyboardInterrupt``.
    """
    def handler(argv):
        raise UserCancelledError("user cancelled via response")

    _stub_handler(monkeypatch, handler)
    assert main(["plan"]) == 130


def test_cancelled_response_does_not_print_traceback(monkeypatch, capsys):
    """A user-initiated cancel is clean control flow — no traceback leaks."""
    def handler(argv):
        raise UserCancelledError("user cancelled via response")

    _stub_handler(monkeypatch, handler)
    rc = main(["plan"])
    captured = capsys.readouterr()
    assert rc == 130
    assert "Traceback" not in captured.err
    assert "Traceback" not in captured.out


# --- exit 2 via UserPausedError (CR-003 fix from W2 review) ----------------


def test_paused_response_maps_to_exit_2(monkeypatch):
    """CR-003 fix — a host response with ``paused: true`` (and
    ``allow_pause=True`` on the prompt) resolves to ``UserPausedError``;
    ``cli.main`` returns exit 2 cleanly, same code as
    ``PausedForInputError`` but with a distinct semantic origin.
    """
    def handler(argv):
        raise UserPausedError("user paused via response")

    _stub_handler(monkeypatch, handler)
    assert main(["plan"]) == 2


def test_paused_response_does_not_print_traceback(monkeypatch, capsys):
    """User-initiated pause is clean control flow — no traceback."""
    def handler(argv):
        raise UserPausedError("user paused via response")

    _stub_handler(monkeypatch, handler)
    rc = main(["plan"])
    captured = capsys.readouterr()
    assert rc == 2
    assert "Traceback" not in captured.err
    assert "Traceback" not in captured.out
