"""Fase 0 T1 — testes da fronteira shell `mem_call`.

TDD estrito: estes testes são escritos PRIMEIRO (vermelho — o módulo
`engine.integrations.mem` ainda não existe), depois a implementação mínima
os torna verdes.

Disciplina de subprocess: o `mem` é um arquivo OPACO invocado por subprocess,
nunca `import mem`. Cada teste que toca o subprocesso real faz monkeypatch de
`subprocess.run` pra capturar argv/env sem executar o binário de verdade.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


def _write_stub_binary(path: Path) -> None:
    """Cria um stub executável no `path` (marca o arquivo como mem vendorizado).

    O conteúdo é irrelevante — `mem_call` resolve o binário por existência +
    bit de execução, não por conteúdo. `subprocess.run` é monkeypatchado nos
    testes que verificam comportamento de runtime.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)


class _FakeCompleted:
    """Stand-in pra `subprocess.CompletedProcess` com os campos que importam."""

    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


# 1 — resolução prefere o binário vendorizado em `.claude/bin/mem`.
def test_resolve_prefers_vendored(tmp_path, monkeypatch):
    from engine.integrations import mem as mem_mod

    vendored = tmp_path / ".claude" / "bin" / "mem"
    _write_stub_binary(vendored)

    captured: dict = {}

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _FakeCompleted(0, stdout="{}")

    # Mesmo com `mem` no PATH, o vendorizado tem precedência.
    monkeypatch.setattr(mem_mod.shutil, "which", lambda _t: "/usr/local/bin/mem")
    monkeypatch.setattr(subprocess, "run", _fake_run)

    result = mem_mod.mem_call(tmp_path, ["doctor"])

    assert result.found is True
    assert captured["cmd"][0] == str(vendored)


# 2 — sem vendorizado, cai pro `shutil.which("mem")`.
def test_resolve_falls_back_to_which(tmp_path, monkeypatch):
    from engine.integrations import mem as mem_mod

    which_path = "/usr/local/bin/mem"
    captured: dict = {}

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _FakeCompleted(0, stdout="{}")

    monkeypatch.setattr(mem_mod.shutil, "which", lambda _t: which_path)
    monkeypatch.setattr(subprocess, "run", _fake_run)

    result = mem_mod.mem_call(tmp_path, ["doctor"])

    assert result.found is True
    assert captured["cmd"][0] == which_path


# 3 — sem vendorizado e sem PATH → found=False, sem crash.
def test_not_found_returns_found_false(tmp_path, monkeypatch):
    from engine.integrations import mem as mem_mod

    monkeypatch.setattr(mem_mod.shutil, "which", lambda _t: None)

    # subprocess.run NÃO deve ser chamado — se for, falha barulhenta.
    def _boom(*_a, **_k):  # pragma: no cover - guard
        raise AssertionError("subprocess.run não deveria rodar sem binário")

    monkeypatch.setattr(subprocess, "run", _boom)

    result = mem_mod.mem_call(tmp_path, ["doctor"])

    assert result.found is False
    assert result.stdout == ""
    assert result.stderr  # mensagem descritiva presente


# 4 — `--json` vem ANTES do subcomando (regression do bug
#     `unrecognized arguments: --json`).
def test_json_flag_precedes_subcommand(tmp_path, monkeypatch):
    from engine.integrations import mem as mem_mod

    vendored = tmp_path / ".claude" / "bin" / "mem"
    _write_stub_binary(vendored)

    captured: dict = {}

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _FakeCompleted(0, stdout="{}")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    mem_mod.mem_call(tmp_path, ["doctor"], json=True)

    cmd = captured["cmd"]
    assert cmd == [str(vendored), "--json", "doctor"]
    # Posicionalmente: --json estritamente antes do subcomando.
    assert cmd.index("--json") < cmd.index("doctor")


# 5 — exit 0 captura stdout e marca found=True.
def test_exit_0_parses_stdout(tmp_path, monkeypatch):
    from engine.integrations import mem as mem_mod

    vendored = tmp_path / ".claude" / "bin" / "mem"
    _write_stub_binary(vendored)

    payload = '{"version": "0.8.1", "ok": true}'

    def _fake_run(cmd, **kwargs):
        return _FakeCompleted(0, stdout=payload)

    monkeypatch.setattr(subprocess, "run", _fake_run)

    result = mem_mod.mem_call(tmp_path, ["doctor"])

    assert result.found is True
    assert result.exit_code == 0
    assert result.stdout == payload


# 6 — exit 2 (não-encontrado) mapeado sem exceção.
def test_exit_2_not_found_mapped(tmp_path, monkeypatch):
    from engine.integrations import mem as mem_mod

    vendored = tmp_path / ".claude" / "bin" / "mem"
    _write_stub_binary(vendored)

    def _fake_run(cmd, **kwargs):
        return _FakeCompleted(2, stdout="", stderr="not found")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    result = mem_mod.mem_call(tmp_path, ["get", "missing-id"])

    # exit 2 é contrato (not-found), não erro: binário resolveu e rodou.
    assert result.exit_code == 2
    assert result.found is True


# 7 — TimeoutExpired → fail-soft, sem propagar exceção.
def test_timeout_fail_soft(tmp_path, monkeypatch):
    from engine.integrations import mem as mem_mod

    vendored = tmp_path / ".claude" / "bin" / "mem"
    _write_stub_binary(vendored)

    def _fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout", 10))

    monkeypatch.setattr(subprocess, "run", _fake_run)

    result = mem_mod.mem_call(tmp_path, ["doctor"], timeout=1)

    assert result.timed_out is True
    assert result.found is True  # binário existe; só não respondeu a tempo
    assert result.stderr  # mensagem de timeout descritiva


# 8 — env do subprocesso é scrubado de sinais de host agêntico.
def test_env_scrubbed(tmp_path, monkeypatch):
    from engine.integrations import mem as mem_mod

    vendored = tmp_path / ".claude" / "bin" / "mem"
    _write_stub_binary(vendored)

    # Polui o env com sinais que NÃO devem vazar pro mem.
    for key in (
        "CLAUDECODE",
        "OPENCODE_VERSION",
        "OPENCODE_SERVER_PASSWORD",
        "CODEX_CLI",
        "CURSOR_AGENT",
    ):
        monkeypatch.setenv(key, "1")
    # Var legítima preservada.
    monkeypatch.setenv("PATH", "/usr/bin")

    captured: dict = {}

    def _fake_run(cmd, **kwargs):
        captured["env"] = kwargs.get("env")
        return _FakeCompleted(0, stdout="{}")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    mem_mod.mem_call(tmp_path, ["doctor"])

    env = captured["env"]
    assert env is not None, "mem_call deve passar env= explícito ao subprocesso"
    for key in ("CLAUDECODE", "OPENCODE_VERSION", "OPENCODE_SERVER_PASSWORD",
                "CODEX_CLI", "CURSOR_AGENT"):
        assert key not in env, f"{key} vazou pro env do mem"
    assert env.get("PATH") == "/usr/bin"
