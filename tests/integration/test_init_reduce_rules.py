"""Task B (W-RULES) — testes de integracao de _reduce_rules.

TDD RED: escritos PRIMEIRO, verificados como FAILING antes da implementacao.
Exercitam o comportamento end-to-end de init._reduce_rules:

- greenfield skip (sem rules → False)
- no-LLM skip (classify None → False, sem sentinel)
- accept: move Tier-1 pro mem + .bak + ponteiro + sentinel
- abort-on-mem-add-fail (H-104/M-201): corpo preservado, sem .bak orfao
- adjust-then-accept (M-202): re-classify com revise + prior
- pause-resume REAL via intent-file (H-101): intent-id determinístico sobrevive
  a re-run
- CR-01: mem add com body começando em '-' (bullet) — usa mem REAL, sem mock
- CR-02: Tier-1 sem mem_note.body → InitError + arquivo-fonte intacto + sem .bak
- WR-01: headings idênticos no mesmo arquivo — só Tier-1 é trimado, Tier-0 preservado

Marcados com `integration` (exercitam multiplos modulos com tmp filesystem).
"""
from __future__ import annotations

import shutil
import subprocess

import pytest
from pathlib import Path
from engine import init
from engine.integrations.mem import MemResult
from engine.ui import intent_state
from engine.utils.paths import mem_asset_path


# ── helpers ──────────────────────────────────────────────────────────────────


def _ok() -> MemResult:
    """MemResult de sucesso (mem add OK)."""
    return MemResult(found=True, exit_code=0, stdout="", stderr="")


def _fail() -> MemResult:
    """MemResult de falha (mem add falhou)."""
    return MemResult(found=True, exit_code=1, stdout="", stderr="erro simulado")


def _consumer(tmp_path: Path) -> Path:
    """Cria uma raiz de projeto com .claude/rules/ e CLAUDE.md minimos."""
    (tmp_path / ".git").mkdir()
    rules = tmp_path / ".claude" / "rules"
    rules.mkdir(parents=True)
    (rules / "reuso.md").write_text(
        "## Reuso\nConsulte o graph antes de criar helper.\n",
        encoding="utf-8",
    )
    (tmp_path / "CLAUDE.md").write_text(
        "# Projeto\n## Gate\nNUNCA commitar sem teste.\n",
        encoding="utf-8",
    )
    return tmp_path


def _vendor_mem_for_test(project_root: Path) -> bool:
    """Vendoriza o mem REAL no projeto de teste (para testes que não mockam mem_call).

    Copia o asset embarcado → .claude/bin/mem (755) e roda 'mem init' para
    criar o estado inicial do banco. Retorna True se tudo OK, False se o
    asset não estiver disponível (skip sinal para o teste).
    """
    asset = mem_asset_path()
    if not asset.is_file():
        return False
    bin_dir = project_root / ".claude" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    mem_dst = bin_dir / "mem"
    shutil.copy2(asset, mem_dst)
    mem_dst.chmod(0o755)
    res = subprocess.run(
        [str(mem_dst), "init"],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        timeout=15,
    )
    return res.returncode == 0


def _pin_intent_file_host(project_root: Path) -> None:
    """Pin host=intent-file via forge-config.yaml e reseta caches."""
    forge_dir = project_root / ".claude" / "forge"
    forge_dir.mkdir(parents=True, exist_ok=True)
    (forge_dir / "forge-config.yaml").write_text(
        "host: intent-file\nschema-version: 1\n",
        encoding="utf-8",
    )
    from engine.host import detect as _host_detect
    _host_detect._clear_cache()
    from engine.ui import intent_state as _is
    _is._reset_log_cache()


# ── testes ───────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_reduce_rules_greenfield_skips(tmp_path: Path) -> None:
    """Sem .claude/rules/ nem CLAUDE.md → retorna False sem tocar nada."""
    (tmp_path / ".git").mkdir()
    assert init._reduce_rules(tmp_path) is False


@pytest.mark.integration
def test_reduce_rules_no_llm_skips(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Host TTY/sem-LLM → classify None → pula com aviso, não trava."""
    c = _consumer(tmp_path)
    monkeypatch.setattr("engine.init.question.classify", lambda *a, **k: None)
    assert init._reduce_rules(c) is False
    assert not (c / ".claude" / ".rules-reduced").exists()


@pytest.mark.integration
def test_reduce_rules_accept_moves_tier1_to_mem_with_bak(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Aceitar: move Tier-1 pro mem, cria .bak, converte em ponteiro, seta sentinel."""
    c = _consumer(tmp_path)
    # classify: seção Reuso é Tier-1; Gate é Tier-0.
    monkeypatch.setattr(
        "engine.init.question.classify",
        lambda *a, **k: [
            {
                "fragment_id": "reuso.md::reuso",
                "tier": 1,
                "rationale": "ref",
                "mem_note": {
                    "type": "reference",
                    "title": "Reuso",
                    "body": "Consulte o graph antes de criar helper.",
                    "tags": ["reuso"],
                },
            },
            {"fragment_id": "CLAUDE.md::gate", "tier": 0, "rationale": "invariante"},
        ],
    )
    monkeypatch.setattr(
        "engine.init.question.ask_three_paths", lambda *a, **k: "a"  # aceitar
    )
    calls: list[list[str]] = []
    monkeypatch.setattr(
        "engine.init.mem_call",
        lambda pr, args, **k: calls.append(list(args)) or _ok(),
    )
    result = init._reduce_rules(c)
    assert result is True
    assert any(a[0] == "add" for a in calls), "mem add deve ser chamado"
    assert (c / ".claude" / "rules" / "reuso.md.bak").exists(), ".bak deve existir (Decisão 24)"
    rule_text = (c / ".claude" / "rules" / "reuso.md").read_text(encoding="utf-8")
    assert "mem find" in rule_text, "arquivo deve virar ponteiro com mem find"
    assert (c / ".claude" / ".rules-reduced").exists(), "sentinel deve existir"


@pytest.mark.integration
def test_reduce_rules_aborts_trim_when_mem_add_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """H-104/M-201: se algum mem add falha, NÃO faz .bak nem trim (dado preservado)."""
    c = _consumer(tmp_path)
    monkeypatch.setattr(
        "engine.init.question.classify",
        lambda *a, **k: [
            {
                "fragment_id": "reuso.md::reuso",
                "tier": 1,
                "rationale": "ref",
                "mem_note": {
                    "type": "reference",
                    "title": "Reuso",
                    "body": "...",
                    "tags": ["reuso"],
                },
            }
        ],
    )
    monkeypatch.setattr(
        "engine.init.question.ask_three_paths", lambda *a, **k: "a"  # aceitar
    )
    monkeypatch.setattr("engine.init.mem_call", lambda pr, args, **k: _fail())
    with pytest.raises(init.InitError):  # IMP-02: _MemAddError é InitError, não RuntimeError cru
        init._reduce_rules(c)
    body = (c / ".claude" / "rules" / "reuso.md").read_text(encoding="utf-8")
    assert "Consulte o graph" in body, "corpo deve estar preservado (sem trim)"
    assert not (c / ".claude" / "rules" / "reuso.md.bak").exists(), "M-201: sem .bak orfao no abort"


@pytest.mark.integration
def test_reduce_rules_revise_incomplete_raises_init_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """IMP-01: se classify(revise=True) omite algum fragmento, InitError é levantado."""
    c = _consumer(tmp_path)
    call_count = 0

    def fake_classify(fragments, *, schema=None, **k):
        nonlocal call_count
        call_count += 1
        schema = schema or {}
        if schema.get("revise"):
            # Retorna classificação incompleta — omite CLAUDE.md::gate.
            return [
                {
                    "fragment_id": "reuso.md::reuso",
                    "tier": 1,
                    "rationale": "ref",
                    "mem_note": {
                        "type": "reference",
                        "title": "Reuso",
                        "body": "x",
                        "tags": ["reuso"],
                    },
                }
            ]
        # 1ª chamada: ambos os fragmentos classificados.
        return [
            {
                "fragment_id": "reuso.md::reuso",
                "tier": 1,
                "rationale": "ref",
                "mem_note": {
                    "type": "reference",
                    "title": "Reuso",
                    "body": "x",
                    "tags": ["reuso"],
                },
            },
            {"fragment_id": "CLAUDE.md::gate", "tier": 0, "rationale": "invariante"},
        ]

    paths_seq = iter(["b"])  # escolhe ajustar → dispara revise
    monkeypatch.setattr("engine.init.question.classify", fake_classify)
    monkeypatch.setattr(
        "engine.init.question.ask_three_paths", lambda *a, **k: next(paths_seq)
    )
    monkeypatch.setattr("engine.init.mem_call", lambda pr, args, **k: _ok())
    with pytest.raises(init.InitError, match="classify \\(revise\\).*incompleto"):
        init._reduce_rules(c)


@pytest.mark.integration
def test_reduce_rules_adjust_then_accept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M-202: 'ajustar' re-classifica (revise) e volta ao 3-caminhos; depois aceita."""
    c = _consumer(tmp_path)
    seen_schemas: list[dict] = []

    def fake_classify(fragments, *, schema=None, **k):
        schema = schema or {}
        seen_schemas.append(schema)
        # 1ª chamada: Gate (CLAUDE.md) como Tier-1 de forma incorreta (humano discorda
        # → escolhe ajustar). Reuso como Tier-1 também.
        # 2ª chamada (revise=True): correção — Gate vira Tier-0, Reuso fica Tier-1.
        revise = schema.get("revise", False)
        result = []
        for frag in fragments:
            fid = frag["id"]
            if fid == "reuso.md::reuso":
                # Sempre Tier-1 (em ambas as rodadas).
                result.append({
                    "fragment_id": fid,
                    "tier": 1,
                    "rationale": "ref",
                    "mem_note": {
                        "type": "reference",
                        "title": "Reuso",
                        "body": "x",
                        "tags": ["reuso"],
                    },
                })
            elif fid == "CLAUDE.md::gate":
                # 1ª: Tier-1 incorreto. 2ª (revise): corrigido para Tier-0.
                tier = 0 if revise else 1
                entry: dict = {"fragment_id": fid, "tier": tier, "rationale": "r"}
                if tier == 1:
                    entry["mem_note"] = {
                        "type": "reference",
                        "title": "Gate",
                        "body": "nunca commitar",
                        "tags": ["gate"],
                    }
                result.append(entry)
            else:
                result.append({"fragment_id": fid, "tier": 0, "rationale": "invariante"})
        return result

    paths_seq = iter(["b", "a"])  # ajustar, depois aceitar
    monkeypatch.setattr("engine.init.question.classify", fake_classify)
    monkeypatch.setattr(
        "engine.init.question.ask_three_paths", lambda *a, **k: next(paths_seq)
    )
    monkeypatch.setattr("engine.init.mem_call", lambda pr, args, **k: _ok())
    result = init._reduce_rules(c)
    assert result is True
    assert any(s.get("revise") for s in seen_schemas), "revisão deve ter ocorrido"
    assert (c / ".claude" / ".rules-reduced").exists()


@pytest.mark.integration
def test_reduce_rules_real_pause_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """H-101: exercita exit-2/re-entry REAL com IntentFileAdapter.

    Prova que o intent-id determinístico sobrevive à re-run (sem deadlock
    intent-mismatch). A 2ª invocação de _reduce_rules NÃO re-pausa no
    classify — consome a response seedada.
    """
    for v in ("CLAUDECODE", "OPENCODE_BIN", "CODEX", "CURSOR_TRACE_ID"):
        monkeypatch.delenv(v, raising=False)
    c = _consumer(tmp_path)
    _pin_intent_file_host(c)

    from engine.ui.question import PausedForInputError
    from engine.utils.paths import forge_state_dir

    # 1ª invocação: classify sem response → pausa (exit 2).
    with pytest.raises(PausedForInputError):
        init._reduce_rules(c)

    state_dir = forge_state_dir(c)
    pending = intent_state.read_pending(c, state_dir=state_dir)
    assert pending is not None, "deve ter escrito o pending"
    assert pending["kind"] == "classify"
    iid = pending["intent-id"]

    # Seed a response: todos Tier-0 (nada vai pro mem — mais simples).
    intent_state.write_response(
        c,
        {
            "schema-version": 1,
            "intent-id": iid,
            "classification": [
                {"fragment_id": fr["id"], "tier": 0, "rationale": "inv"}
                for fr in pending["fragments"]
            ],
        },
        state_dir=state_dir,
    )

    # 2ª invocação (re-run): parse determinístico → mesmo intent-id → consome
    # a response. Como todos são Tier-0, _reduce_rules retorna False sem ask_three_paths.
    # O ponto provado: NÃO re-pausa no classify.
    result = init._reduce_rules(c)
    assert result is False  # sem Tier-1 → nada movido


@pytest.mark.integration
def test_reduce_rules_cr01_bullet_body_with_real_mem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CR-01: body começando com '-' (bullet markdown) não quebra o mem add real.

    Fecha a cegueira de mock: exercita mem_call SEM mock — usa o mem REAL
    embarcado em engine/assets/mem/mem. Confirma que o `--` antes do body
    posicional impede o argparse do mem de tratar '-' como flag.

    Assertions:
    - _reduce_rules retorna True (redução aplicada).
    - mem find consegue achar a nota gravada (prova que add foi a disco).
    - O arquivo-fonte vira ponteiro com 'mem find'.
    - .bak criado e sentinel gravados.
    """
    if not mem_asset_path().is_file():
        pytest.skip("mem asset não disponível — skip CR-01 real-mem test")

    c = _consumer(tmp_path)
    # Substitui reuso.md por um body começando com '-' (bullet).
    (c / ".claude" / "rules" / "reuso.md").write_text(
        "## Reuso\n- consulte o graph antes\n- verifique inventory/\n",
        encoding="utf-8",
    )
    ok = _vendor_mem_for_test(c)
    assert ok, "falha ao inicializar mem no projeto de teste"

    monkeypatch.setattr(
        "engine.init.question.classify",
        lambda *a, **k: [
            {
                "fragment_id": "reuso.md::reuso",
                "tier": 1,
                "rationale": "referência — enxugável pro mem",
                "mem_note": {
                    "type": "reference",
                    "title": "Reuso bullet",
                    "body": "- consulte o graph antes\n- verifique inventory/",
                    "tags": ["reuso"],
                },
            },
            {"fragment_id": "CLAUDE.md::gate", "tier": 0, "rationale": "invariante"},
        ],
    )
    monkeypatch.setattr(
        "engine.init.question.ask_three_paths", lambda *a, **k: "a"  # aceitar
    )
    # NÃO mocka mem_call — usa o mem REAL para fechar a cegueira de mock.

    result = init._reduce_rules(c)
    assert result is True, "_reduce_rules deve retornar True (redução aplicada)"

    # Prova que a nota foi gravada no mem real (find retorna a nota).
    mem_bin = str(c / ".claude" / "bin" / "mem")
    find_res = subprocess.run(
        [mem_bin, "find", "reuso"],
        cwd=str(c),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert find_res.returncode == 0, f"mem find falhou: {find_res.stderr}"
    assert "Reuso bullet" in find_res.stdout, "nota deve estar no mem após add"

    # Arquivo-fonte virou ponteiro.
    rule_text = (c / ".claude" / "rules" / "reuso.md").read_text(encoding="utf-8")
    assert "mem find" in rule_text, "arquivo deve conter ponteiro mem find"
    # .bak e sentinel.
    assert (c / ".claude" / "rules" / "reuso.md.bak").exists(), ".bak deve existir"
    assert (c / ".claude" / ".rules-reduced").exists(), "sentinel deve existir"


@pytest.mark.integration
def test_reduce_rules_cr02_missing_mem_note_body_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CR-02: Tier-1 sem mem_note.body → InitError + arquivo-fonte intacto + sem .bak.

    O engine deve recusar o trim ANTES de qualquer operação destrutiva quando
    um item Tier-1 não carrega body no mem_note. Sem esse gate, o trim
    apagaria conteúdo sem gravá-lo no mem (perda de conhecimento silenciosa).
    """
    c = _consumer(tmp_path)
    monkeypatch.setattr(
        "engine.init.question.classify",
        lambda *a, **k: [
            {
                "fragment_id": "reuso.md::reuso",
                "tier": 1,
                "rationale": "ref",
                "mem_note": {
                    "type": "reference",
                    "title": "Reuso",
                    # body deliberadamente ausente (vazio/None).
                    "body": "",
                    "tags": ["reuso"],
                },
            },
            {"fragment_id": "CLAUDE.md::gate", "tier": 0, "rationale": "invariante"},
        ],
    )
    monkeypatch.setattr(
        "engine.init.question.ask_three_paths", lambda *a, **k: "a"  # aceitar
    )
    # mem_call mockado — não deve ser chamado (CR-02 aborta ANTES do add).
    add_called = []
    monkeypatch.setattr(
        "engine.init.mem_call",
        lambda pr, args, **k: add_called.append(args) or _ok(),
    )

    with pytest.raises(init.InitError, match="sem mem_note.body"):
        init._reduce_rules(c)

    # Arquivo-fonte deve estar intacto.
    body = (c / ".claude" / "rules" / "reuso.md").read_text(encoding="utf-8")
    assert "Consulte o graph" in body, "corpo deve estar preservado (sem trim)"
    # Sem .bak orfão.
    assert not (c / ".claude" / "rules" / "reuso.md.bak").exists(), "sem .bak orfão"
    # mem add NÃO deve ter sido invocado.
    assert not add_called, "mem_call não deve ser chamado quando body está vazio"


@pytest.mark.integration
def test_reduce_rules_wr01_duplicate_headings_trim_only_tier1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WR-01: dois headings idênticos no mesmo arquivo — só o Tier-1 é trimado.

    Arquivo com '## Reuso' duas vezes: 1ª ocorrência é Tier-1 (vai pro mem),
    2ª é Tier-0 (invariante, deve permanecer intacta). Sem desambiguação por
    ocorrência, o trim casaria AMBAS as seções e destruiria a Tier-0.
    """
    c = _consumer(tmp_path)
    # Cria arquivo com dois headings idênticos: 1ª Tier-1, 2ª Tier-0.
    (c / ".claude" / "rules" / "reuso.md").write_text(
        "## Reuso\nConsulte o graph antes de criar helper.\n\n"
        "## Reuso\nEsta seção é invariante e NUNCA deve ser removida.\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "engine.init.question.classify",
        lambda *a, **k: [
            # 1ª ocorrência de "## Reuso" → Tier-1 (id: "reuso.md::reuso")
            {
                "fragment_id": "reuso.md::reuso",
                "tier": 1,
                "rationale": "referência enxugável",
                "mem_note": {
                    "type": "reference",
                    "title": "Reuso-1",
                    "body": "Consulte o graph antes de criar helper.",
                    "tags": ["reuso"],
                },
            },
            # 2ª ocorrência de "## Reuso" → Tier-0 (id: "reuso.md::reuso#2")
            {
                "fragment_id": "reuso.md::reuso#2",
                "tier": 0,
                "rationale": "invariante always-on",
            },
            {"fragment_id": "CLAUDE.md::gate", "tier": 0, "rationale": "invariante"},
        ],
    )
    monkeypatch.setattr(
        "engine.init.question.ask_three_paths", lambda *a, **k: "a"  # aceitar
    )
    calls: list[list[str]] = []
    monkeypatch.setattr(
        "engine.init.mem_call",
        lambda pr, args, **k: calls.append(list(args)) or _ok(),
    )

    result = init._reduce_rules(c)
    assert result is True

    rule_text = (c / ".claude" / "rules" / "reuso.md").read_text(encoding="utf-8")
    # A 2ª seção Tier-0 deve permanecer intacta.
    assert "NUNCA deve ser removida" in rule_text, (
        "seção Tier-0 (2ª ocorrência) deve estar intacta"
    )
    # A 1ª seção Tier-1 deve ter virado ponteiro (body original removido).
    assert "Consulte o graph antes de criar helper" not in rule_text, (
        "corpo Tier-1 (1ª ocorrência) deve ter sido substituído pelo ponteiro"
    )
    assert "mem find" in rule_text, "ponteiro 'mem find' deve aparecer"
