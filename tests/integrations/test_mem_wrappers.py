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


# ── Task 1 (6b): mem_inbox_add ────────────────────────────────────────────


def test_inbox_add_builds_correct_argv(tmp_path, monkeypatch):
    from engine.integrations import mem
    _stub(tmp_path / ".claude" / "bin" / "mem")
    cap = _patch_run(monkeypatch, 0, stdout='"01ABC"')
    res = mem.mem_inbox_add(
        tmp_path,
        title="use-stateflow",
        body="Use MutableStateFlow para screen state",
        mem_type="reference",
        importance=4,
        tags="auth,kotlin",
        source="forge-evolve:P-001",
        origin="manual",
    )
    assert res.ok is True
    # argv esperado (sem o binário — index 1 em diante):
    # --json inbox add --type reference -t use-stateflow
    # --importance 4 --tags auth,kotlin --source forge-evolve:P-001 --origin manual
    # -- Use MutableStateFlow para screen state
    cmd = cap["cmd"]
    assert cmd[1] == "--json"
    assert cmd[2] == "inbox"
    assert cmd[3] == "add"
    assert "--type" in cmd and cmd[cmd.index("--type") + 1] == "reference"
    assert "-t" in cmd and cmd[cmd.index("-t") + 1] == "use-stateflow"
    assert "--importance" in cmd and cmd[cmd.index("--importance") + 1] == "4"
    assert "--tags" in cmd and cmd[cmd.index("--tags") + 1] == "auth,kotlin"
    assert "--source" in cmd and cmd[cmd.index("--source") + 1] == "forge-evolve:P-001"
    assert "--origin" in cmd and cmd[cmd.index("--origin") + 1] == "manual"
    # -- separador ANTES do body (obrigatório — lição W-RULES)
    assert "--" in cmd
    dash_dash_idx = cmd.index("--")
    assert cmd[dash_dash_idx + 1] == "Use MutableStateFlow para screen state"


def test_inbox_add_minimal_argv(tmp_path, monkeypatch):
    """Sem opcionais: só --type, -t, -- body."""
    from engine.integrations import mem
    _stub(tmp_path / ".claude" / "bin" / "mem")
    cap = _patch_run(monkeypatch, 0, stdout='"01XYZ"')
    res = mem.mem_inbox_add(
        tmp_path,
        title="t",
        body="desc",
        mem_type="reference",
    )
    assert res.ok is True
    cmd = cap["cmd"]
    # Opcionais ausentes
    assert "--importance" not in cmd
    assert "--tags" not in cmd
    assert "--source" not in cmd
    # --origin default é "manual" — deve estar presente
    assert "--origin" in cmd and cmd[cmd.index("--origin") + 1] == "manual"
    # -- separador presente
    assert "--" in cmd
    assert cmd[-1] == "desc"


def test_inbox_add_body_with_leading_dash_safe(tmp_path, monkeypatch):
    """Body começando com '-' não quebra o argparse do mem por causa do '--'."""
    from engine.integrations import mem
    _stub(tmp_path / ".claude" / "bin" / "mem")
    cap = _patch_run(monkeypatch, 0, stdout='"01DEF"')
    mem.mem_inbox_add(tmp_path, title="t", body="--option-like body", mem_type="reference")
    cmd = cap["cmd"]
    dash_dash_idx = cmd.index("--")
    assert cmd[dash_dash_idx + 1] == "--option-like body"


def test_inbox_add_degrades_soft_when_binary_missing(tmp_path, monkeypatch):
    from engine.integrations import mem
    monkeypatch.setattr(mem.shutil, "which", lambda _t: None)
    res = mem.mem_inbox_add(tmp_path, title="t", body="b", mem_type="reference")
    assert res.ok is False
    assert res.data is None
    assert res.message  # mensagem 3-caminhos presente


# ── Teste real-mem (MOCK-BLINDNESS): path de escrita contra binário real ──


import os as _os


@pytest.mark.skipif(
    not (_os.path.isfile("/tmp/.claude/bin/mem") or _os.path.isfile(
        str(Path(__file__).resolve().parents[2] / ".claude" / "bin" / "mem")
    )),
    reason="binário mem não disponível — pule em CI sem vendorização",
)
def test_inbox_add_real_mem_roundtrip(tmp_path):
    """Teste real-mem: add via mem_inbox_add + asserta que aparece no inbox list.

    Copia o binário vendorizado do repo pra tmp_path/.claude/bin/mem pra
    isolar o banco de dados do inbox de produção. Sem mock — o binário real
    processa o argv e escreve no banco.
    """
    import shutil as _shutil
    from engine.integrations import mem

    # Localiza o binário vendorizado do repo (não o de /tmp usado pelo dev)
    repo_root = Path(__file__).resolve().parents[2]
    src_bin = repo_root / ".claude" / "bin" / "mem"
    if not src_bin.is_file():
        pytest.skip("binário vendorizado não encontrado no repo")

    dest_bin = tmp_path / ".claude" / "bin" / "mem"
    dest_bin.parent.mkdir(parents=True, exist_ok=True)
    _shutil.copy2(str(src_bin), str(dest_bin))
    dest_bin.chmod(0o755)

    unique_title = f"test-6b-real-mem-{tmp_path.name}"
    res = mem.mem_inbox_add(
        tmp_path,
        title=unique_title,
        body="Descrição do padrão de teste real-mem da sub-onda 6b.",
        mem_type="reference",
        importance=3,
        source="forge-evolve:TEST-REAL",
        origin="manual",
    )
    assert res.ok is True, f"mem_inbox_add falhou: {res.message}"

    # Asserta que a nota aparece no inbox list
    from engine.integrations.mem import mem_call
    list_result = mem_call(tmp_path, ["inbox", "list"])
    assert list_result.found is True
    assert list_result.exit_code == 0
    import json as _json_rt
    items = _json_rt.loads(list_result.stdout or "[]")
    titles = [it.get("title") for it in items if isinstance(it, dict)]
    assert unique_title in titles, f"nota não aparece no inbox list: {titles}"
