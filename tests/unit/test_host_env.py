import os
import pytest
from engine.host.env import (
    detect_claude_code, detect_opencode, detect_codex, detect_cursor, detect_any_agentic,
)


def test_detect_claude_code_truthy(monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "1")
    assert detect_claude_code() is True


def test_detect_claude_code_falsy(monkeypatch):
    monkeypatch.delenv("CLAUDECODE", raising=False)
    assert detect_claude_code() is False


def test_detect_opencode_via_prefix(monkeypatch):
    monkeypatch.setenv("OPENCODE_VERSION", "1.0")
    assert detect_opencode() is True


def test_detect_codex(monkeypatch):
    monkeypatch.setenv("CODEX_CLI", "1")
    assert detect_codex() is True


def test_detect_any_agentic_truthy(monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "1")
    assert detect_any_agentic() is True


def test_detect_any_agentic_falsy(monkeypatch):
    for v in ("CLAUDECODE", "OPENCODE_VERSION", "CODEX_CLI", "CURSOR_AGENT"):
        monkeypatch.delenv(v, raising=False)
    assert detect_any_agentic() is False
