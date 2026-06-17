import os
from pathlib import Path
import pytest
from engine.host.detect import detect_host, _clear_cache
from engine.host.adapter import HostName


def test_detect_via_config_override(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDECODE", raising=False)
    _clear_cache()
    cfg = tmp_path / ".claude" / "forge" / "forge-config.yaml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text("host: opencode\n")
    assert detect_host(tmp_path) == HostName.OPENCODE


def test_detect_via_env_claude_code(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "1")
    _clear_cache()
    assert detect_host(tmp_path) == HostName.CLAUDE_CODE


def test_detect_fallback_intent_file(tmp_path, monkeypatch):
    for v in ("CLAUDECODE", "OPENCODE_VERSION", "CODEX_CLI", "CURSOR_AGENT"):
        monkeypatch.delenv(v, raising=False)
    _clear_cache()
    # sys.stdin.isatty() é False em pytest → fallback intent_file
    assert detect_host(tmp_path) in (HostName.TTY, HostName.INTENT_FILE)


def test_detect_via_env_opencode_when_var_present(tmp_path, monkeypatch):
    # Ramo aspiracional: COM OPENCODE_* no env (e sem CLAUDECODE), detect_host
    # resolve OPENCODE. Trava a precedência; este caso é raro hoje porque o
    # opencode não injeta OPENCODE_* em subprocessos (research §3).
    for v in ("CLAUDECODE", "CODEX_CLI", "CURSOR_AGENT", "FORGE_FORCE_INTENT_MODE"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("OPENCODE_CONFIG", "/home/dev/.config/opencode/config.json")
    _clear_cache()
    assert detect_host(tmp_path) == HostName.OPENCODE


def test_detect_opencode_real_env_falls_to_intent_file(tmp_path, monkeypatch):
    # Trava o comportamento REAL do opencode: sem nenhum sinal de env
    # (incluindo OPENCODE_*, que o opencode não injeta — research §3) e com
    # stdin não-tty (subprocesso pipado), detect_host cai em INTENT_FILE.
    # Este é o adapter que opencode efetivamente recebe (Veredito B).
    for v in ("CLAUDECODE", "OPENCODE_VERSION", "OPENCODE_CONFIG", "CODEX_CLI",
              "CURSOR_AGENT", "FORGE_FORCE_INTENT_MODE"):
        monkeypatch.delenv(v, raising=False)
    for k in [k for k in os.environ if k.startswith("OPENCODE_")]:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr("sys.stdin", type("_FakeNonTTY", (), {"isatty": lambda self: False})())
    _clear_cache()
    assert detect_host(tmp_path) == HostName.INTENT_FILE


def test_detect_cache_same_process(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "1")
    _clear_cache()
    first = detect_host(tmp_path)
    monkeypatch.delenv("CLAUDECODE")
    second = detect_host(tmp_path)
    assert first == second  # cache survives env change


# --- FORGE_FORCE_INTENT_MODE escape-hatch (drift-1 spec §439) ---------------


def test_force_intent_mode_overrides_tty(tmp_path, monkeypatch):
    """FORGE_FORCE_INTENT_MODE=1 + isatty True → INTENT_FILE, não TTY."""
    for v in ("CLAUDECODE", "OPENCODE_VERSION", "CODEX_CLI", "CURSOR_AGENT"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("FORGE_FORCE_INTENT_MODE", "1")
    monkeypatch.setattr("sys.stdin", type("_FakeTTY", (), {"isatty": lambda self: True})())
    _clear_cache()
    assert detect_host(tmp_path) == HostName.INTENT_FILE


def test_force_intent_mode_config_still_wins(tmp_path, monkeypatch):
    """Config explícito `host: tty` vence sobre FORGE_FORCE_INTENT_MODE."""
    for v in ("CLAUDECODE", "OPENCODE_VERSION", "CODEX_CLI", "CURSOR_AGENT"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("FORGE_FORCE_INTENT_MODE", "1")
    cfg = tmp_path / ".claude" / "forge" / "forge-config.yaml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text("host: tty\n")
    _clear_cache()
    assert detect_host(tmp_path) == HostName.TTY


def test_force_intent_mode_absent_preserves_tty(tmp_path, monkeypatch):
    """Sem FORGE_FORCE_INTENT_MODE + isatty True → TTY (comportamento normal)."""
    for v in ("CLAUDECODE", "OPENCODE_VERSION", "CODEX_CLI", "CURSOR_AGENT",
              "FORGE_FORCE_INTENT_MODE"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr("sys.stdin", type("_FakeTTY", (), {"isatty": lambda self: True})())
    _clear_cache()
    assert detect_host(tmp_path) == HostName.TTY
