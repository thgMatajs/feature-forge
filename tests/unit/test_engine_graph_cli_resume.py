"""Resume-from-checkpoint tests for ``engine.graph_cli`` (DRIFT-1 W2.T3b).

Outcome C per W2.T0: per-subcommand ``_GraphCliCheckpoint`` dataclass
following ``_InitCheckpoint`` template (``engine/init.py:100-108``).
Lives in this module — NO import from ``engine.qa.checkpoint``.

graph_cli expoe 7 callsites interativos (menu ``ask`` + 6 prompts de
handler tipo ``ask_text``/``ask``). O resume cobre o cenario canonico
em que o host pausou no menu e re-invoca com a response no disco.

Refs:
- docs/superpowers/specs/drift-1-intent-protocol.md §3, §5, §8
- .planning/drift-1/checkpoint-audit.json (action=add-new, reuse_path=init-pattern)
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from engine import graph_cli
from engine.ui import question


# ── Smoke — dataclass + helpers existem (add-new) ────────────────────────────


def test_graph_cli_checkpoint_dataclass_exists() -> None:
    """_GraphCliCheckpoint dataclass surface must mirror _InitCheckpoint shape."""
    cp_cls = getattr(graph_cli, "_GraphCliCheckpoint", None)
    assert cp_cls is not None, "_GraphCliCheckpoint not declared in engine.graph_cli"
    cp = cp_cls(
        step="step-menu",
        at="2026-06-10T00:00:00Z",
        project_root="/tmp/foo",
    )
    assert cp.step == "step-menu"
    assert getattr(cp, "intent_id", "<missing>") is None
    assert getattr(cp, "handler_key", "<missing>") is None


def test_graph_cli_save_load_clear_roundtrip(tmp_forge_project: Path) -> None:
    """_save/_load/_clear_graph_cli_checkpoint sao idempotentes per outcome C."""
    save = getattr(graph_cli, "_save_graph_cli_checkpoint", None)
    load = getattr(graph_cli, "_load_graph_cli_checkpoint", None)
    clear = getattr(graph_cli, "_clear_graph_cli_checkpoint", None)
    assert save is not None, "_save_graph_cli_checkpoint missing"
    assert load is not None, "_load_graph_cli_checkpoint missing"
    assert clear is not None, "_clear_graph_cli_checkpoint missing"

    cp = graph_cli._GraphCliCheckpoint(
        step="step-menu",
        at="2026-06-10T00:00:00Z",
        project_root=str(tmp_forge_project),
        intent_id="abc-789",
        handler_key="3",
    )
    save(cp)
    loaded = load(tmp_forge_project)
    assert isinstance(loaded, dict)
    assert loaded.get("step") == "step-menu"
    assert loaded.get("intent-id") == "abc-789"
    assert loaded.get("handler-key") == "3"

    clear(tmp_forge_project)
    assert load(tmp_forge_project) is None


# ── Comportamento — resume consome response do menu, nao re-prompta ─────────


def _seed_graph_db_and_config(project_root: Path) -> None:
    """graph_cli.run sai cedo se graph.db ou workflow-config ausente.

    Schema vazio basta pra passar pelo check ``graph_db_path.exists()`` —
    o handler escolhido (orphan-files, choice=3) so faz read em tabelas
    que podem nao existir; o handler captura via except Exception, mas
    rapido o suficiente pra nao bloquear o teste.
    """
    cfg_dir = project_root / ".claude"
    cfg_dir.mkdir(exist_ok=True)
    (cfg_dir / "workflow-config.yaml").write_text(
        "schema-version: 1\n"
        "identity:\n"
        "  project-slug: test-graph-cli-resume\n",
        encoding="utf-8",
    )
    db_path = cfg_dir / "graph.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE IF NOT EXISTS _bootstrap(k TEXT)")
    conn.commit()
    conn.close()


def test_resume_from_checkpoint(
    tmp_forge_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cenario canonico de resume — checkpoint do menu + response.json correspondente.

    Sequencia simulada:
      1. Invocacao A pausou no menu ``ask`` (gravou pending + checkpoint
         com intent_id da pergunta canonica).
      2. Host escreveu ``forge-response.json`` com mesmo intent_id +
         value="3" (orphan-files — handler nao prompta nada).
      3. Invocacao B (este test): graph_cli.run carrega checkpoint,
         descobre intent_id; ``question.ask`` consome response, retorna
         "3" sem raise; handler ``_q_orphans`` roda sem precisar de
         ``ask_text``.
      4. Checkpoint apagado apos clean completion.
    """
    _seed_graph_db_and_config(tmp_forge_project)
    monkeypatch.chdir(tmp_forge_project)

    # Stage 1 — calcula o intent-id deterministico do menu canonico.
    # Opcoes seguem exatamente o pattern em graph_cli.py:run().
    menu_options = {
        "1":  "similar-features {slug}     (Q1)",
        "2":  "blast-radius {file...}     (Q2)",
        "3":  "orphan-files               (Q3)",
        "4":  "symbols {module}           (Q4)",
        "5":  "ds-used-in {slug}          (Q5)",
        "6":  "i18n-used-in {slug}        (Q6)",
        "7":  "routes {slug}              (Q7)",
        "8":  "di-deps {class}            (Q8)",
        "9":  "tests-for {file}           (Q9)",
        "10": "commits {slug}             (Q10)",
        "11": "reusable-helpers {types}   (Q11)",
        "12": "dup-within-module          (Q12)",
        "13": "dup-cross-module           (Q13)",
        "14": "kmp-migration              (Q14)",
        "15": "near-duplicates            (Q15)",
        "16": "redundant-platform         (Q16)",
        "17": "dup-ts-helpers             (Q17)",
        "r":  "reuse-findings (combined)",
        "c":  "cancelar",
    }
    intent_id = question._stable_intent_id(
        "ask",
        "Qual query?",
        menu_options,
        extra={"default": "3", "min-selected": None, "validator-hint": None},
    )

    # Stage 2 — host escreveu response.json + checkpoint do graph_cli.
    state_dir = tmp_forge_project / ".claude" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    response_payload = {
        "schema-version": 1,
        "intent-id": intent_id,
        "value": "3",
        "responded-at": "2026-06-10T00:01:00Z",
    }
    (state_dir / "forge-response.json").write_text(
        json.dumps(response_payload), encoding="utf-8"
    )
    cp = graph_cli._GraphCliCheckpoint(
        step="step-menu",
        at="2026-06-10T00:00:30Z",
        project_root=str(tmp_forge_project),
        intent_id=intent_id,
        handler_key=None,
    )
    graph_cli._save_graph_cli_checkpoint(cp)

    # Sanity — checkpoint + response no disco antes de rodar.
    assert graph_cli._load_graph_cli_checkpoint(tmp_forge_project) is not None
    assert (state_dir / "forge-response.json").exists()

    # Stage 3 — invoca graph_cli.run([]). question.ask deve consumir o
    # response, voltar "3" (orphan-files), handler roda sem prompts e
    # retorna. Exit code 0 ou 1 (graph.db vazio nao tem tabelas — o
    # handler captura via except Exception e retorna 1; aceitavel pro
    # contract resume).
    rc = graph_cli.run([])

    assert rc in (0, 1), f"unexpected exit code from graph_cli.run: {rc}"

    # Resume contract: forge-response.json e consumido (question.ask
    # apaga em _clear_state).
    assert not (state_dir / "forge-response.json").exists(), (
        "response file should be consumed/cleared after successful resume"
    )

    # Checkpoint deve ser apagado apos run completar (clean completion).
    assert graph_cli._load_graph_cli_checkpoint(tmp_forge_project) is None, (
        "checkpoint should be cleared on clean completion"
    )
