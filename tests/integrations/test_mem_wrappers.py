"""W-ROUTE 6a Task 2 — testes da camada típica de wrappers sobre mem_call.

TDD: escritos PRIMEIRO. Monkeypatcham `subprocess.run` (via o mesmo caminho
de mem_call) pra capturar o argv montado sem rodar o binário real.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


def _stub(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)


class _Fake:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _patch_run(monkeypatch, returncode: int, stdout: str = "", stderr: str = "") -> dict:
    captured: dict = {}

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _Fake(returncode, stdout=stdout, stderr=stderr)

    monkeypatch.setattr(subprocess, "run", _fake_run)
    return captured


def test_mem_find_builds_find_argv(tmp_path, monkeypatch):
    from engine.integrations import mem
    _stub(tmp_path / ".claude" / "bin" / "mem")
    cap = _patch_run(monkeypatch, 0, stdout='[{"id":"X","score":0.5,"type":"feedback","title":"t","author":"a"}]')
    res = mem.mem_find(tmp_path, "reuse", limit=3)
    assert res.ok is True
    assert res.data == [{"id": "X", "score": 0.5, "type": "feedback", "title": "t", "author": "a"}]
    # argv: <bin> --json find reuse -k 3
    assert cap["cmd"][1:] == ["--json", "find", "reuse", "-k", "3"]


def test_mem_find_type_filter(tmp_path, monkeypatch):
    from engine.integrations import mem
    _stub(tmp_path / ".claude" / "bin" / "mem")
    cap = _patch_run(monkeypatch, 0, stdout="[]")
    mem.mem_find(tmp_path, "q", mem_type="decision")
    assert "--type" in cap["cmd"] and "decision" in cap["cmd"]


def test_mem_get_returns_note(tmp_path, monkeypatch):
    from engine.integrations import mem
    _stub(tmp_path / ".claude" / "bin" / "mem")
    cap = _patch_run(monkeypatch, 0, stdout='{"id":"X","title":"t","body":"b","type":"feedback"}')
    res = mem.mem_get(tmp_path, "X")
    assert res.ok is True
    assert res.data["body"] == "b"
    assert cap["cmd"][1:] == ["--json", "get", "X"]


def test_mem_get_exit2_is_not_found_contract(tmp_path, monkeypatch):
    from engine.integrations import mem
    _stub(tmp_path / ".claude" / "bin" / "mem")
    _patch_run(monkeypatch, 2, stdout="", stderr="not found")
    res = mem.mem_get(tmp_path, "missing")
    # exit 2 é contrato (not-found), não erro: ok=True, data=None.
    assert res.ok is True
    assert res.data is None


def test_mem_stats_parses(tmp_path, monkeypatch):
    from engine.integrations import mem
    _stub(tmp_path / ".claude" / "bin" / "mem")
    _patch_run(monkeypatch, 0, stdout='{"total":3,"live":3,"by_type":{"feedback":3}}')
    res = mem.mem_stats(tmp_path)
    assert res.ok is True
    assert res.data["total"] == 3


def test_mem_brief_budget(tmp_path, monkeypatch):
    from engine.integrations import mem
    _stub(tmp_path / ".claude" / "bin" / "mem")
    cap = _patch_run(monkeypatch, 0, stdout='[{"id":"X","type":"decision","line":"l"}]')
    res = mem.mem_brief(tmp_path, budget=200)
    assert res.ok is True
    assert cap["cmd"][1:] == ["--json", "brief", "--budget", "200"]


def test_mem_evolve_apply_flag(tmp_path, monkeypatch):
    from engine.integrations import mem
    _stub(tmp_path / ".claude" / "bin" / "mem")
    cap = _patch_run(monkeypatch, 0, stdout='{"archive":[],"dup_clusters":[],"applied":0}')
    mem.mem_evolve(tmp_path, apply=True)
    assert cap["cmd"][1:] == ["--json", "evolve", "--apply"]


def test_wrapper_degrades_soft_when_binary_missing(tmp_path, monkeypatch):
    from engine.integrations import mem
    monkeypatch.setattr(mem.shutil, "which", lambda _t: None)
    res = mem.mem_find(tmp_path, "q")
    assert res.ok is False
    assert res.data is None
    assert res.message  # mensagem 3-caminhos presente
