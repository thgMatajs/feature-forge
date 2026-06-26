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

Marcados com `integration` (exercitam multiplos modulos com tmp filesystem).
"""
from __future__ import annotations

import pytest
from pathlib import Path
from engine import init
from engine.integrations.mem import MemResult
from engine.ui import intent_state


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
