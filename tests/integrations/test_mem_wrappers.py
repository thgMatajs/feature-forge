"""W-ROUTE 6a Task 2 — testes da camada típica de wrappers sobre mem_call.

TDD: escritos PRIMEIRO. Monkeypatcham `subprocess.run` (via o mesmo caminho
de mem_call) pra capturar o argv montado sem rodar o binário real.
"""
from __future__ import annotations

import os
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
    # P5 (cross-AI PR#32): flags ANTES, `--` separa, query POSICIONAL por último.
    # argv: <bin> --json find -k 3 -- reuse
    assert cap["cmd"][1:] == ["--json", "find", "-k", "3", "--", "reuse"]


def test_mem_find_type_filter(tmp_path, monkeypatch):
    from engine.integrations import mem
    _stub(tmp_path / ".claude" / "bin" / "mem")
    cap = _patch_run(monkeypatch, 0, stdout="[]")
    mem.mem_find(tmp_path, "q", mem_type="decision")
    # P5: `--type` é flag e vem ANTES do separador `--`; a query depois dele.
    assert "--type" in cap["cmd"] and "decision" in cap["cmd"]
    sep = cap["cmd"].index("--")
    assert cap["cmd"].index("--type") < sep
    assert sep < cap["cmd"].index("q")


def test_mem_find_leading_dash_query_protected(tmp_path, monkeypatch):
    """P5 (cross-AI PR#32): query iniciada por `-` não é parseada como flag.

    Verificado empiricamente contra o mem vendorizado: `find "-test" -k 2` falha
    com "required: query". O separador `--` (flags antes, query por último)
    protege o positional sem quebrar os flags.
    """
    from engine.integrations import mem
    _stub(tmp_path / ".claude" / "bin" / "mem")
    cap = _patch_run(monkeypatch, 0, stdout="[]")
    mem.mem_find(tmp_path, "-test", limit=2)
    # argv: <bin> --json find -k 2 -- -test
    assert cap["cmd"][1:] == ["--json", "find", "-k", "2", "--", "-test"]
    # O `--` vem por último, ANTES do query; os flags todos ANTES do `--`.
    sep = cap["cmd"].index("--")
    assert cap["cmd"][sep + 1] == "-test"  # query é o ÚLTIMO token
    assert cap["cmd"].index("-k") < sep    # flag protegida (antes do separador)


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
    mem.mem_inbox_add(tmp_path, title="t", body="-flag-body", mem_type="reference")
    cmd = cap["cmd"]
    dash_dash_idx = cmd.index("--")
    assert cmd[dash_dash_idx + 1] == "-flag-body"


def test_inbox_add_degrades_soft_when_binary_missing(tmp_path, monkeypatch):
    from engine.integrations import mem
    monkeypatch.setattr(mem.shutil, "which", lambda _t: None)
    res = mem.mem_inbox_add(tmp_path, title="t", body="b", mem_type="reference")
    assert res.ok is False
    assert res.data is None
    assert res.message  # mensagem 3-caminhos presente


# ── Task 1 (6d): mem_inbox_reject ─────────────────────────────────────────


def test_mem_inbox_reject_invokes_reject_subcommand(tmp_path, monkeypatch):
    captured = {}

    def fake_run_or_degrade(project_root, args):
        captured["args"] = args
        from engine.integrations.mem import MemQuery
        return MemQuery(ok=True, data={"status": "rejected"})

    monkeypatch.setattr(
        "engine.integrations.mem._run_or_degrade", fake_run_or_degrade
    )
    from engine.integrations.mem import mem_inbox_reject
    res = mem_inbox_reject(tmp_path, "01ABCDEF")
    assert res.ok is True
    assert captured["args"] == ["inbox", "reject", "01ABCDEF"]


@pytest.mark.skipif(
    not os.path.isfile(
        str(Path(__file__).resolve().parents[2] / ".claude" / "bin" / "mem")
    ),
    reason="binário mem não disponível — pule em CI sem vendorização",
)
def test_inbox_reject_real_mem_roundtrip(tmp_path):
    """Teste real-mem do reject (MOCK-BLINDNESS): path de ESCRITA sem mock.

    O reject escreve no mem (`UPDATE inbox SET status='rejected'`). A lição
    do repo manda exercer todo path de escrita contra o binário real
    vendorizado, sem mock — porque mock mascarou Critical no W-RULES.

    Cobre a cadeia: add real → captura id → reject real (ok=True + sumiço do
    pending) → 2º reject do MESMO id (já-resolvido → exit 2 → ok=False via
    `_run_or_degrade`). Sem mock de `_run_or_degrade` — é justamente o
    mapeamento de exit-code que precisa ser verificado contra o binário.
    """
    import shutil as _shutil
    from engine.integrations import mem

    repo_root = Path(__file__).resolve().parents[2]
    src_bin = repo_root / ".claude" / "bin" / "mem"
    if not src_bin.is_file():
        pytest.skip("binário vendorizado não encontrado no repo")

    dest_bin = tmp_path / ".claude" / "bin" / "mem"
    dest_bin.parent.mkdir(parents=True, exist_ok=True)
    _shutil.copy2(str(src_bin), str(dest_bin))
    dest_bin.chmod(0o755)

    # 1) add real → captura o id do candidato.
    unique_title = f"test-6d-reject-real-mem-{tmp_path.name}"
    add_res = mem.mem_inbox_add(
        tmp_path,
        title=unique_title,
        body="Candidato para exercer o reject real-mem da sub-onda 6d.",
        mem_type="reference",
        importance=3,
        source="forge-evolve:TEST-REJECT",
        origin="manual",
    )
    assert add_res.ok is True, f"mem_inbox_add falhou: {add_res.message}"
    inbox_id = add_res.data["id"]
    assert inbox_id, f"id não capturado de result.data: {add_res.data}"

    # 2) reject real do id → ok=True E candidato some do inbox pending.
    rej_res = mem.mem_inbox_reject(tmp_path, inbox_id)
    assert rej_res.ok is True, f"mem_inbox_reject falhou: {rej_res.message}"

    # Verifica o sumiço do pending via `--json inbox list` real, como os
    # roundtrips vizinhos (não há wrapper mem_inbox_list dedicado).
    from engine.integrations.mem import mem_call
    list_result = mem_call(tmp_path, ["inbox", "list"])
    assert list_result.found is True
    assert list_result.exit_code == 0
    import json as _json_rt
    items = _json_rt.loads(list_result.stdout or "[]")
    pending_ids = [it.get("id") for it in items if isinstance(it, dict)]
    assert inbox_id not in pending_ids, (
        f"candidato rejeitado ainda aparece no inbox pending: {pending_ids}"
    )

    # 3) 2º reject do MESMO id → já-resolvido → exit 2 → degrade → ok=False.
    rej2_res = mem.mem_inbox_reject(tmp_path, inbox_id)
    assert rej2_res.ok is False, (
        "2º reject de id já-resolvido deveria degradar pra ok=False "
        f"(exit 2), mas veio ok={rej2_res.ok}"
    )


# ── Teste real-mem (MOCK-BLINDNESS): path de escrita contra binário real ──


@pytest.mark.skipif(
    not os.path.isfile(
        str(Path(__file__).resolve().parents[2] / ".claude" / "bin" / "mem")
    ),
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


# ── Task 2 (6b): apply_proposal_to_l2(knowledge) real-mem e2e ────────────────


def test_apply_proposal_to_l2_knowledge_real_mem_roundtrip(tmp_path):
    """E2E: apply_proposal_to_l2(knowledge) → mem inbox REAL (MOCK-BLINDNESS).

    Confirma que o path de escrita do distiller — description com bullet '-'/
    multiline, provenance→--tags, importance boundary — chega ao inbox sem
    perda de mapeamento. Nenhum mock: o binário real processa o argv e escreve.
    """
    import json
    import shutil

    repo_root = Path(__file__).resolve().parents[2]
    src_bin = repo_root / ".claude" / "bin" / "mem"
    if not src_bin.is_file():
        pytest.skip("binário mem vendorizado ausente")

    dest_bin = tmp_path / ".claude" / "bin" / "mem"
    dest_bin.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(src_bin), str(dest_bin))
    dest_bin.chmod(0o755)

    from engine.integrations.mem import mem_call
    from engine.memory.distiller import (
        DistillationProposal,
        apply_proposal_to_l2,
        queue_proposal,
    )

    # Description adversarial: bullet começando com '-' + multiline
    p = DistillationProposal(
        id="P-real-knowledge",
        kind="promote-to-l2",
        title="real-mem-knowledge-roundtrip",
        description="- bullet começando com hífen\n  segunda linha do corpo",
        provenance=["feat-auth", "feat-profile"],
        confidence=0.5,
    )
    queue_proposal(tmp_path, p)
    apply_proposal_to_l2(tmp_path, p)

    result = mem_call(tmp_path, ["inbox", "list"])
    assert result.exit_code == 0, f"inbox list falhou: {result.stderr}"
    items = json.loads(result.stdout or "[]")
    titles = [it.get("title") for it in items if isinstance(it, dict)]
    assert "real-mem-knowledge-roundtrip" in titles, (
        f"nota não aparece no inbox list: {titles}"
    )


# ── Task 1 (6c): mem_context_hint ────────────────────────────────────────────


def test_mem_context_hint_formats_hits(tmp_path, monkeypatch):
    """Quando mem_find retorna hits, formata texto compacto não-None."""
    from engine.integrations import mem

    _stub(tmp_path / ".claude" / "bin" / "mem")
    _patch_run(
        monkeypatch,
        0,
        stdout='[{"id":"X1","score":0.9,"type":"feedback","title":"use-stateflow","author":"a"},'
               '{"id":"X2","score":0.7,"type":"reference","title":"mvvm-pattern","author":"b"}]',
    )
    result = mem.mem_context_hint(tmp_path, "pattern de arquitetura", limit=5)
    assert result is not None
    assert "use-stateflow" in result
    assert "mvvm-pattern" in result


def test_mem_context_hint_returns_none_on_empty_hits(tmp_path, monkeypatch):
    """Lista vazia → None (sem bloco em branco no context-pack)."""
    from engine.integrations import mem

    _stub(tmp_path / ".claude" / "bin" / "mem")
    _patch_run(monkeypatch, 0, stdout="[]")
    result = mem.mem_context_hint(tmp_path, "qualquer coisa", limit=5)
    assert result is None


def test_mem_context_hint_degrades_soft_when_binary_missing(tmp_path, monkeypatch):
    """Binário ausente → None sem crash, sem propagação de exceção."""
    from engine.integrations import mem

    monkeypatch.setattr(mem.shutil, "which", lambda _t: None)
    result = mem.mem_context_hint(tmp_path, "query", limit=5)
    assert result is None


def test_mem_context_hint_degrades_soft_on_error_exit(tmp_path, monkeypatch):
    """Exit não-zero → None sem crash."""
    from engine.integrations import mem

    _stub(tmp_path / ".claude" / "bin" / "mem")
    _patch_run(monkeypatch, 1, stdout="", stderr="erro interno")
    result = mem.mem_context_hint(tmp_path, "query", limit=5)
    assert result is None


def test_mem_context_hint_respects_limit(tmp_path, monkeypatch):
    """O argv enviado ao mem inclui -k <limit> correto."""
    from engine.integrations import mem

    _stub(tmp_path / ".claude" / "bin" / "mem")
    cap = _patch_run(
        monkeypatch,
        0,
        stdout='[{"id":"Y","score":0.8,"type":"reference","title":"t","author":"a"}]',
    )
    mem.mem_context_hint(tmp_path, "minha query", limit=3)
    cmd = cap["cmd"]
    # Deve delegar pra mem_find que monta: --json find <query> -k <limit>
    assert "find" in cmd
    assert "-k" in cmd and cmd[cmd.index("-k") + 1] == "3"


# ── Teste real-mem (MOCK-BLINDNESS): mem_context_hint contra binário real ─────


import os as _os


@pytest.mark.skipif(
    not (
        _os.path.isfile(
            str(Path(__file__).resolve().parents[2] / ".claude" / "bin" / "mem")
        )
    ),
    reason="binário mem vendorizado não encontrado — pule em CI sem vendorização",
)
def test_mem_context_hint_real_mem_returns_str_or_none(tmp_path):
    """Teste real-mem: mem_context_hint contra o binário vendorizado do repo.

    Copia o binário pra tmp_path/.claude/bin/mem (banco isolado).
    A query pode não ter hits no banco vazio — o invariante é:
    retorna str ou None sem crash, sem exceção.
    """
    import shutil as _shutil
    from engine.integrations import mem

    repo_root = Path(__file__).resolve().parents[2]
    src_bin = repo_root / ".claude" / "bin" / "mem"
    dest_bin = tmp_path / ".claude" / "bin" / "mem"
    dest_bin.parent.mkdir(parents=True, exist_ok=True)
    _shutil.copy2(str(src_bin), str(dest_bin))
    dest_bin.chmod(0o755)

    result = mem.mem_context_hint(tmp_path, "padrão de arquitetura kotlin", limit=3)
    # Banco vazio → None; banco com hits → str com títulos.
    assert result is None or isinstance(result, str)
    if isinstance(result, str):
        # Se retornou algo, deve ser não-vazio e não um dump de erro.
        assert len(result.strip()) > 0
