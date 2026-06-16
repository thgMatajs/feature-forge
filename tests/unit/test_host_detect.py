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


def test_detect_cache_same_process(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "1")
    _clear_cache()
    first = detect_host(tmp_path)
    monkeypatch.delenv("CLAUDECODE")
    second = detect_host(tmp_path)
    assert first == second  # cache survives env change
