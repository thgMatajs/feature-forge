"""Resume-from-checkpoint tests for ``engine.memory_cli`` (DRIFT-1 W2.T3b).

Outcome C per W2.T0: per-subcommand ``_MemoryCliCheckpoint`` dataclass
following ``_InitCheckpoint`` template (``engine/init.py:100-108``).
Lives in this module — NO import from ``engine.qa.checkpoint``.

memory_cli expoe 11 callsites interativos (menu ask, paginacao confirm,
inspect-L1/L3 ask + ask_text, search ask_text, forget-L2 ask_text +
duas confirms, distill-L2 ask). O resume cobre o cenario canonico em
que o host pausou no menu top-level e re-invoca com response no disco.

Refs:
- docs/superpowers/specs/drift-1-intent-protocol.md §3, §5, §8
- .planning/drift-1/checkpoint-audit.json (action=add-new, reuse_path=init-pattern)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine import memory_cli
from engine.ui import question


# ── Smoke — dataclass + helpers existem (add-new) ────────────────────────────


def test_memory_cli_checkpoint_dataclass_exists() -> None:
    """_MemoryCliCheckpoint dataclass surface must mirror _InitCheckpoint shape."""
    cp_cls = getattr(memory_cli, "_MemoryCliCheckpoint", None)
    assert cp_cls is not None, "_MemoryCliCheckpoint not declared in engine.memory_cli"
    cp = cp_cls(
        step="step-menu",
        at="2026-06-10T00:00:00Z",
        project_root="/tmp/foo",
    )
    assert cp.step == "step-menu"
    assert getattr(cp, "intent_id", "<missing>") is None
    assert getattr(cp, "submenu", "<missing>") is None
    assert getattr(cp, "entry_id", "<missing>") is None


def test_memory_cli_save_load_clear_roundtrip(tmp_forge_project: Path) -> None:
    """_save/_load/_clear_memory_cli_checkpoint sao idempotentes per outcome C."""
    save = getattr(memory_cli, "_save_memory_cli_checkpoint", None)
    load = getattr(memory_cli, "_load_memory_cli_checkpoint", None)
    clear = getattr(memory_cli, "_clear_memory_cli_checkpoint", None)
    assert save is not None, "_save_memory_cli_checkpoint missing"
    assert load is not None, "_load_memory_cli_checkpoint missing"
    assert clear is not None, "_clear_memory_cli_checkpoint missing"

    cp = memory_cli._MemoryCliCheckpoint(
        step="step-submenu:5",
        at="2026-06-10T00:00:00Z",
        project_root=str(tmp_forge_project),
        intent_id="def-321",
        submenu="5",
        entry_id="L2-007",
    )
    save(cp)
    loaded = load(tmp_forge_project)
    assert isinstance(loaded, dict)
    assert loaded.get("step") == "step-submenu:5"
    assert loaded.get("intent-id") == "def-321"
    assert loaded.get("submenu") == "5"
    assert loaded.get("entry-id") == "L2-007"

    clear(tmp_forge_project)
    assert load(tmp_forge_project) is None


# ── Comportamento — resume consome response do menu, nao re-prompta ─────────


def _seed_workflow_config(project_root: Path) -> None:
    """memory_cli.run exige workflow-config.yaml — escreve um minimo."""
    cfg_dir = project_root / ".claude"
    cfg_dir.mkdir(exist_ok=True)
    (cfg_dir / "workflow-config.yaml").write_text(
        "schema-version: 1\n"
        "identity:\n"
        "  project-slug: test-memory-cli-resume\n",
        encoding="utf-8",
    )


def test_resume_from_checkpoint(
    tmp_forge_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cenario canonico de resume — checkpoint do menu + response.json correspondente.

    Sequencia simulada:
      1. Invocacao A pausou no menu ``ask`` (gravou pending + checkpoint
         com intent_id da pergunta canonica).
      2. Host escreveu ``forge-response.json`` com mesmo intent_id +
         value="c" (cancelar — submenu sem prompts internos, exit limpo).
      3. Invocacao B (este test): memory_cli.run carrega checkpoint,
         descobre intent_id; ``question.ask`` consome response, retorna
         "c" sem raise; run retorna 0 sem prompts adicionais.
      4. Checkpoint apagado apos clean completion.

    Escolhemos "c" (cancelar) em vez de um submenu real (1-7) pra
    manter o test focado no contract de resume sem ter de simular
    estado L2/L1/L3 minimo. Cobertura dos prompts internos sai via
    test_commands_memory.py + integration.
    """
    _seed_workflow_config(tmp_forge_project)
    monkeypatch.chdir(tmp_forge_project)

    # Stage 1 — calcula o intent-id deterministico do menu canonico.
    menu_options = {
        "1": "inspect L2-project          (paginated)",
        "2": "inspect L1 {slug}",
        "3": "inspect L3 auto-memory      (MEMORY.md proxy)",
        "4": "search                       (substring L1+L2+L3)",
        "5": "forget L2 entry             (confirm dupla)",
        "6": "distill L2                  (apenas em overflow)",
        "7": "export L2 for context-pack  (stdout)",
        "c": "cancelar",
    }
    intent_id = question._stable_intent_id(
        "ask",
        "O que olhar?",
        menu_options,
        extra={"default": "1", "min-selected": None, "validator-hint": None},
    )

    # Stage 2 — host escreveu response.json + checkpoint do memory_cli.
    state_dir = tmp_forge_project / ".claude" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    response_payload = {
        "schema-version": 1,
        "intent-id": intent_id,
        "value": "c",
        "responded-at": "2026-06-10T00:01:00Z",
    }
    (state_dir / "forge-response.json").write_text(
        json.dumps(response_payload), encoding="utf-8"
    )
    cp = memory_cli._MemoryCliCheckpoint(
        step="step-menu",
        at="2026-06-10T00:00:30Z",
        project_root=str(tmp_forge_project),
        intent_id=intent_id,
        submenu=None,
    )
    memory_cli._save_memory_cli_checkpoint(cp)

    # Sanity — checkpoint + response no disco antes de rodar.
    assert memory_cli._load_memory_cli_checkpoint(tmp_forge_project) is not None
    assert (state_dir / "forge-response.json").exists()

    # Stage 3 — invoca memory_cli.run([]). question.ask deve consumir o
    # response, voltar "c" (cancelar), run retorna 0 sem prompts.
    rc = memory_cli.run([])

    assert rc == 0, f"unexpected exit code from memory_cli.run: {rc}"

    # Resume contract: forge-response.json e consumido (question.ask
    # apaga em _clear_state).
    assert not (state_dir / "forge-response.json").exists(), (
        "response file should be consumed/cleared after successful resume"
    )

    # Checkpoint deve ser apagado apos run completar (clean completion).
    assert memory_cli._load_memory_cli_checkpoint(tmp_forge_project) is None, (
        "checkpoint should be cleared on clean completion"
    )
