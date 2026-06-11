"""Resume-from-checkpoint tests for ``engine.undo`` (DRIFT-1 W2.T3b).

Outcome C per W2.T0: per-subcommand ``_UndoCheckpoint`` dataclass
following ``_InitCheckpoint`` template (``engine/init.py:100-108``).
Lives in this module — NO import from ``engine.qa.checkpoint``.

undo expoe 16 callsites interativos (menu ask, confirms multi-step em
init/reconfigure/task-commit/evolve/delete-feature, ask_text em
evolve-id/abort-reason). O resume cobre o cenario canonico em que o
host pausou no menu top-level e re-invoca com response no disco.

Refs:
- docs/superpowers/specs/drift-1-intent-protocol.md §3, §5, §8
- .planning/drift-1/checkpoint-audit.json (action=add-new, reuse_path=init-pattern)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine import undo
from engine.ui import question


# ── Smoke — dataclass + helpers existem (add-new) ────────────────────────────


def test_undo_checkpoint_dataclass_exists() -> None:
    """_UndoCheckpoint dataclass surface must mirror _InitCheckpoint shape."""
    cp_cls = getattr(undo, "_UndoCheckpoint", None)
    assert cp_cls is not None, "_UndoCheckpoint not declared in engine.undo"
    cp = cp_cls(
        step="step-menu",
        at="2026-06-10T00:00:00Z",
        project_root="/tmp/foo",
    )
    assert cp.step == "step-menu"
    assert getattr(cp, "intent_id", "<missing>") is None
    assert getattr(cp, "target_kind", "<missing>") is None
    assert getattr(cp, "feature_slug", "<missing>") is None
    assert getattr(cp, "confirm_level", "<missing>") is None


def test_undo_save_load_clear_roundtrip(tmp_forge_project: Path) -> None:
    """_save/_load/_clear_undo_checkpoint sao idempotentes per outcome C."""
    save = getattr(undo, "_save_undo_checkpoint", None)
    load = getattr(undo, "_load_undo_checkpoint", None)
    clear = getattr(undo, "_clear_undo_checkpoint", None)
    assert save is not None, "_save_undo_checkpoint missing"
    assert load is not None, "_load_undo_checkpoint missing"
    assert clear is not None, "_clear_undo_checkpoint missing"

    cp = undo._UndoCheckpoint(
        step="step-target:6",
        at="2026-06-10T00:00:00Z",
        project_root=str(tmp_forge_project),
        intent_id="ghi-654",
        target_kind="6",
        feature_slug="lembrete-rega",
        confirm_level="confirm-1",
    )
    save(cp)
    loaded = load(tmp_forge_project)
    assert isinstance(loaded, dict)
    assert loaded.get("step") == "step-target:6"
    assert loaded.get("intent-id") == "ghi-654"
    assert loaded.get("target-kind") == "6"
    assert loaded.get("feature-slug") == "lembrete-rega"
    assert loaded.get("confirm-level") == "confirm-1"

    clear(tmp_forge_project)
    assert load(tmp_forge_project) is None


# ── Comportamento — resume consome response do menu, nao re-prompta ─────────


def _seed_workflow_config(project_root: Path) -> None:
    """undo.run exige workflow-config.yaml — escreve um minimo."""
    cfg_dir = project_root / ".claude"
    cfg_dir.mkdir(exist_ok=True)
    (cfg_dir / "workflow-config.yaml").write_text(
        "schema-version: 1\n"
        "identity:\n"
        "  project-slug: test-undo-resume\n",
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
         value="c" (cancelar — sem prompts adicionais).
      3. Invocacao B (este test): undo.run carrega checkpoint, descobre
         intent_id; ``question.ask`` consome response, retorna "c" sem
         raise; run retorna 0.
      4. Checkpoint apagado apos clean completion.

    Test escolhe "c" (cancelar) em vez de um target real (1-7) pra
    evitar simular history JSONL, l1-state, git repo. Cobertura dos
    prompts internos sai via test_commands_undo.py + integration.
    """
    _seed_workflow_config(tmp_forge_project)
    monkeypatch.chdir(tmp_forge_project)

    # Stage 1 — calcula o intent-id deterministico do menu canonico.
    menu_options = {
        "1": "last — última ação reversível (default)",
        "2": "reconfigure — reverter último reconfigure",
        "3": "task commit — reverter commit (git revert)",
        "4": "evolve apply — reverter aplicação L2",
        "5": "abort feature — marcar feature como aborted (terminal)",
        "6": "delete feature artifacts — apagar pasta (irreversível)",
        "7": "init — apagar .claude/ inteira (raríssimo)",
        "c": "cancelar",
    }
    intent_id = question._stable_intent_id(
        "ask",
        "O que deseja reverter?",
        menu_options,
        extra={"default": "1", "min-selected": None, "validator-hint": None},
    )

    # Stage 2 — host escreveu response.json + checkpoint do undo.
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
    cp = undo._UndoCheckpoint(
        step="step-menu",
        at="2026-06-10T00:00:30Z",
        project_root=str(tmp_forge_project),
        intent_id=intent_id,
        target_kind=None,
    )
    undo._save_undo_checkpoint(cp)

    # Sanity — checkpoint + response no disco antes de rodar.
    assert undo._load_undo_checkpoint(tmp_forge_project) is not None
    assert (state_dir / "forge-response.json").exists()

    # Stage 3 — invoca undo.run([]). question.ask deve consumir o
    # response, voltar "c" (cancelar), run retorna 0 sem prompts.
    rc = undo.run([])

    assert rc == 0, f"unexpected exit code from undo.run: {rc}"

    # Resume contract: forge-response.json e consumido (question.ask
    # apaga em _clear_state).
    assert not (state_dir / "forge-response.json").exists(), (
        "response file should be consumed/cleared after successful resume"
    )

    # Checkpoint deve ser apagado apos run completar (clean completion).
    assert undo._load_undo_checkpoint(tmp_forge_project) is None, (
        "checkpoint should be cleared on clean completion"
    )
