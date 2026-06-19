import os
import pytest
from engine.host.env import (
    detect_claude_code, detect_opencode, detect_codex, detect_cursor,
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


def test_detect_opencode_via_config_var(monkeypatch):
    # OPENCODE_CONFIG é a var que mais provavelmente existiria no env do
    # processo opencode (config file path). Travamos o caso positivo.
    for v in ("OPENCODE_VERSION", "OPENCODE_CONFIG"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("OPENCODE_CONFIG", "/home/dev/.config/opencode/config.json")
    assert detect_opencode() is True


def test_detect_opencode_real_subprocess_env_is_false(monkeypatch):
    # Trava o comportamento documentado: na prática, um subprocesso forge
    # invocado pelo opencode NÃO vê nenhum OPENCODE_* no env, porque o
    # opencode não injeta vars identificadoras nos subprocessos que spawna
    # (docs/research/opencode-tool-api.md §3 + issue sst/opencode#1775).
    # Logo, detect_opencode() retorna False nesse cenário — e opencode cai
    # no fallback TTY→INTENT_FILE em detect_host.
    for k in [k for k in os.environ if k.startswith("OPENCODE_")]:
        monkeypatch.delenv(k, raising=False)
    assert detect_opencode() is False


def test_detect_codex(monkeypatch):
    monkeypatch.setenv("CODEX_CLI", "1")
    assert detect_codex() is True


def test_detect_codex_requires_underscore(monkeypatch):
    """C-49b (PR22-B-02): o detector usa prefixo preciso CODEX_ — uma var
    CODEX-cru não-relacionada (CODEXBASE, CODEX) NÃO dispara falso-positivo."""
    monkeypatch.delenv("CODEX_CLI", raising=False)
    monkeypatch.setenv("CODEXBASE", "1")
    assert detect_codex() is False


def test_detect_cursor(monkeypatch):
    monkeypatch.setenv("CURSOR_AGENT", "1")
    assert detect_cursor() is True
