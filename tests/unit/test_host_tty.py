"""Unit tests — ``TtyAdapter`` in-process stdin prompt loop.

Cobre o contrato do adapter TTY in-process (Wave 2, Task 2.2): substitui
o ``tty_bridge`` subprocess-loop por leitura direta de stdin, SEM
pending.json (spec §4 + success criterion #5). Os testes mockam
``sys.stdin`` (via ``StringIO``) + ``sys.stdin.isatty`` pra exercitar o
loop sem um PTY real — o caminho PTY real fica no e2e
(``tests/e2e/test_tty_adapter_pty.py``).

Refs:
  - ``docs/superpowers/specs/2026-06-16-v1-3-pilot-ready-design.md`` §4
  - ``engine/host/adapters/tty.py``
  - ``engine/ui/_stdin_prompt.py``
"""
from __future__ import annotations

from io import StringIO
from unittest.mock import patch

import pytest

from engine.host.adapter import (
    AskKind,
    AskResult,
    HostName,
    UserCancelledError,
    UserPausedError,
)
from engine.host.adapters.tty import TtyAdapter


def _stdin(text: str):
    """Build a ``StringIO`` whose ``isatty`` reports True.

    ``patch("sys.stdin", buf)`` swaps the whole object, so the adapter's
    ``sys.stdin.isatty()`` guard reads ``buf.isatty`` — set it True so the
    in-TTY path runs. ``input()`` reads from the patched ``sys.stdin``.
    """
    buf = StringIO(text)
    buf.isatty = lambda: True  # type: ignore[method-assign]
    return buf


# ── name / construction ─────────────────────────────────────────────────────


def test_tty_adapter_name_is_tty(tmp_path):
    adapter = TtyAdapter(project_root=tmp_path)
    assert adapter.name is HostName.TTY


# ── ask — happy path ────────────────────────────────────────────────────────


def test_tty_ask_reads_stdin(tmp_path):
    adapter = TtyAdapter(project_root=tmp_path)
    with patch("sys.stdin", _stdin("a\n")):
        result = adapter.ask(
            kind=AskKind.ASK,
            question="Qual?",
            options={"a": "Opção A", "b": "Opção B"},
            default=None,
            allow_pause=True,
        )
    assert isinstance(result, AskResult)
    assert result.value == "a"
    assert result.paused is False


def test_tty_ask_accepts_label_match(tmp_path):
    adapter = TtyAdapter(project_root=tmp_path)
    with patch("sys.stdin", _stdin("Opção B\n")):
        result = adapter.ask(
            kind=AskKind.ASK,
            question="Qual?",
            options={"a": "Opção A", "b": "Opção B"},
            default=None,
            allow_pause=True,
        )
    # Label typed → resolves to the option key.
    assert result.value == "b"


def test_tty_ask_empty_line_with_default(tmp_path):
    adapter = TtyAdapter(project_root=tmp_path)
    with patch("sys.stdin", _stdin("\n")):
        result = adapter.ask(
            kind=AskKind.ASK,
            question="Qual?",
            options={"a": "Opção A", "b": "Opção B"},
            default="a",
            allow_pause=True,
        )
    assert result.value == "a"
    assert result.from_default is True


# ── ask — guard / pause / cancel ────────────────────────────────────────────


def test_tty_ask_non_tty_raises(tmp_path):
    adapter = TtyAdapter(project_root=tmp_path)
    buf = StringIO("a\n")
    buf.isatty = lambda: False  # type: ignore[method-assign]
    with patch("sys.stdin", buf):
        with pytest.raises(RuntimeError, match="non-TTY"):
            adapter.ask(
                kind=AskKind.ASK,
                question="Qual?",
                options={"a": "A"},
                default=None,
                allow_pause=True,
            )


def test_tty_ask_pause_token_raises_user_paused(tmp_path):
    adapter = TtyAdapter(project_root=tmp_path)
    with patch("sys.stdin", _stdin("para\n")):
        with pytest.raises(UserPausedError):
            adapter.ask(
                kind=AskKind.ASK,
                question="Qual?",
                options={"a": "A", "b": "B"},
                default=None,
                allow_pause=True,
            )


def test_tty_ask_eof_raises_user_cancelled(tmp_path):
    adapter = TtyAdapter(project_root=tmp_path)
    # Empty buffer → input() hits EOF immediately.
    with patch("sys.stdin", _stdin("")):
        with pytest.raises(UserCancelledError):
            adapter.ask(
                kind=AskKind.ASK,
                question="Qual?",
                options={"a": "A", "b": "B"},
                default=None,
                allow_pause=True,
            )


def test_tty_ask_three_invalid_raises_user_cancelled(tmp_path):
    adapter = TtyAdapter(project_root=tmp_path)
    # Three garbage tokens exhaust _MAX_INVALID_ATTEMPTS.
    with patch("sys.stdin", _stdin("x\ny\nz\n")):
        with pytest.raises(UserCancelledError):
            adapter.ask(
                kind=AskKind.ASK,
                question="Qual?",
                options={"a": "A", "b": "B"},
                default=None,
                allow_pause=True,
            )


def test_tty_ask_recovers_after_invalid(tmp_path):
    adapter = TtyAdapter(project_root=tmp_path)
    # First token invalid, second valid → returns the valid one.
    with patch("sys.stdin", _stdin("zzz\nb\n")):
        result = adapter.ask(
            kind=AskKind.ASK,
            question="Qual?",
            options={"a": "A", "b": "B"},
            default=None,
            allow_pause=True,
        )
    assert result.value == "b"


# ── ask_text ────────────────────────────────────────────────────────────────


def test_tty_ask_text_reads_line(tmp_path):
    adapter = TtyAdapter(project_root=tmp_path)
    with patch("sys.stdin", _stdin("um nome qualquer\n")):
        value = adapter.ask_text(prompt="Nome?", default=None)
    assert value == "um nome qualquer"


def test_tty_ask_text_empty_with_default(tmp_path):
    adapter = TtyAdapter(project_root=tmp_path)
    with patch("sys.stdin", _stdin("\n")):
        value = adapter.ask_text(prompt="Nome?", default="fallback")
    assert value == "fallback"


def test_tty_ask_text_pause_token_raises(tmp_path):
    adapter = TtyAdapter(project_root=tmp_path)
    with patch("sys.stdin", _stdin("quit\n")):
        with pytest.raises(UserPausedError):
            adapter.ask_text(prompt="Nome?", default=None)


def test_tty_ask_text_eof_cancels(tmp_path):
    adapter = TtyAdapter(project_root=tmp_path)
    with patch("sys.stdin", _stdin("")):
        with pytest.raises(UserCancelledError):
            adapter.ask_text(prompt="Nome?", default=None)


# ── ask_multi ───────────────────────────────────────────────────────────────


def test_tty_ask_multi_comma_separated(tmp_path):
    adapter = TtyAdapter(project_root=tmp_path)
    with patch("sys.stdin", _stdin("a, c\n")):
        result = adapter.ask_multi(
            question="Quais?",
            options={"a": "A", "b": "B", "c": "C"},
        )
    assert result == ["a", "c"]


def test_tty_ask_multi_single(tmp_path):
    adapter = TtyAdapter(project_root=tmp_path)
    with patch("sys.stdin", _stdin("b\n")):
        result = adapter.ask_multi(
            question="Quais?",
            options={"a": "A", "b": "B"},
        )
    assert result == ["b"]


def test_tty_ask_multi_pause_token_raises(tmp_path):
    adapter = TtyAdapter(project_root=tmp_path)
    with patch("sys.stdin", _stdin("pausa\n")):
        with pytest.raises(UserPausedError):
            adapter.ask_multi(
                question="Quais?",
                options={"a": "A", "b": "B"},
            )


# ── no pending.json written (in-process invariant) ──────────────────────────


def test_tty_ask_writes_no_pending_file(tmp_path):
    """Success criterion #5 — TtyAdapter is in-process, never touches state."""
    adapter = TtyAdapter(project_root=tmp_path)
    with patch("sys.stdin", _stdin("a\n")):
        adapter.ask(
            kind=AskKind.ASK,
            question="Qual?",
            options={"a": "A"},
            default=None,
            allow_pause=True,
        )
    # No .claude/forge/state/forge-pending.json — adapter is in-process.
    pending = tmp_path / ".claude" / "forge" / "state" / "forge-pending.json"
    assert not pending.exists()


# ── registry wiring ─────────────────────────────────────────────────────────


def test_resolve_adapter_registers_tty(tmp_path):
    """``_resolve_adapter`` returns a ``TtyAdapter`` when host is TTY."""
    from engine.host import registry
    from engine.ui import question

    registry.clear_registry()
    with patch("engine.host.detect.detect_host", return_value=HostName.TTY):
        adapter = question._resolve_adapter(tmp_path)
    assert isinstance(adapter, TtyAdapter)
    registry.clear_registry()
