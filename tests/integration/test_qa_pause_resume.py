"""Integration — Ctrl+C pause + resume (Decisão 27).

Wave 8 Task 8.6: aspirational tests do contrato pause/resume pra ``forge
qa``. Decisão 27 estabelece "pause = ``deferred`` auto-resumable; abort
terminal só via ``forge undo``".

**Estado atual**: ``engine.qa`` ainda NÃO implementa checkpoint/resume —
o handler em ``engine/qa/__init__.py`` é stateless por design (Phases
1+2+4 são dispatch externo via Claude Code Agent, e Phase 4 synthesis
roda sobre findings já materializados em ``findings/*.json``). A
persistência de progresso parcial entre interrupções vive na convenção
de filesystem (a run tree existe → findings parciais persistem; nova
invocação cria nova run tree).

Por isso os 3 tests aqui são ``@pytest.mark.skip`` documentando o
contrato esperado quando o feature aterrissar (Wave futura ou
follow-up). Mantém o arquivo na suite como contract spec ativa —
quando alguém implementar o checkpoint, basta remover os ``skip``.

Marker: integration (slow). Excluído da rapid lane.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

_PENDING_REASON = (
    "pause/resume implementation pending — engine.qa atualmente é "
    "stateless (Phases LLM são dispatch externo). Reabilitar quando "
    "checkpoint.json + resume detection aterrissarem."
)


@pytest.fixture
def qa_pause_project(tmp_path: Path) -> Path:
    """Project root mínimo com feature stub pra exercícios de pause/resume."""
    proj = tmp_path / "qa-pause-pilot"
    (proj / ".git").mkdir(parents=True)
    feat = (
        proj
        / "docs"
        / "feature-implementation-workflow"
        / "features"
        / "pause-feature"
    )
    feat.mkdir(parents=True)
    (feat / "feature-spec.yaml").write_text(
        "schema-version: 1\nslug: pause-feature\n", encoding="utf-8"
    )
    return proj


@pytest.mark.skip(reason=_PENDING_REASON)
def test_checkpoint_written_between_phase_1_and_phase_2(
    qa_pause_project: Path,
) -> None:
    """Ctrl+C entre Phase 1 e Phase 2 → checkpoint.json com phase_completed=1.

    Contrato esperado:
    - Hook SIGINT no conductor escreve ``<run_tree.root>/checkpoint.json``
      com payload ``{"phase_completed": 1, "findings_partial": [...]}``
    - Arquivo serializado atomicamente (tmp + os.replace) pra Ctrl+C
      duplo não corromper
    - Findings parciais de Phase 1 preservados em ``findings/phase-1-*.json``
    """
    from engine.qa import run_qa  # noqa: F401 — placeholder pra import-check

    # Quando implementado: simular SIGINT via mock no dispatch loop.
    # Assert checkpoint.json existe + payload coerente.
    assert qa_pause_project.exists()  # placeholder


@pytest.mark.skip(reason=_PENDING_REASON)
def test_resume_detects_checkpoint_and_reuses_phase_1_findings(
    qa_pause_project: Path,
) -> None:
    """Nova invocação detecta checkpoint + retoma sem regenerar findings.

    Contrato esperado:
    - Run tree pré-existente com ``checkpoint.json`` + findings parciais
    - Nova invocação de ``run_qa`` detecta checkpoint, pula Phase 1
      (findings reused), executa Phase 2+
    - Auditoria preservada: nenhum dispatch redundante registrado
    """
    # Pre-seed: run tree + checkpoint.json apontando phase_completed=1
    run_dir = (
        qa_pause_project
        / ".planning"
        / "qa"
        / "pause-feature"
        / "2026-06-04T12-00-00Z-abcd"
    )
    run_dir.mkdir(parents=True)
    (run_dir / "findings").mkdir()
    (run_dir / "findings" / "phase-1-coverage.json").write_text(
        json.dumps({"findings": [{"vector": "coverage-gap", "severity": "info"}]}),
        encoding="utf-8",
    )
    (run_dir / "checkpoint.json").write_text(
        json.dumps({"phase_completed": 1, "scope": "feature", "target": "pause-feature"}),
        encoding="utf-8",
    )

    # Quando implementado: invocar run_qa e assertar que phase 1 NÃO
    # foi re-dispatched (mocking conductor + counting calls).
    assert (run_dir / "checkpoint.json").exists()


@pytest.mark.skip(reason=_PENDING_REASON)
def test_corrupt_checkpoint_offers_three_paths_remediation(
    qa_pause_project: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Checkpoint JSON inválido → 3-caminhos (ignore+restart / abort / inspect).

    Contrato esperado (Disciplina 1 — 3-caminhos pattern):
    - ``checkpoint.json`` mal-formado (JSON inválido OU shape inesperado)
    - Handler detecta + apresenta 3 caminhos via mensagem mentor calmo:
        1) Ignorar checkpoint e recomeçar do zero
        2) Abortar invocação (volta pro caller pra inspeção manual)
        3) Path absoluto do checkpoint pra ``cat`` / debug
    """
    run_dir = (
        qa_pause_project
        / ".planning"
        / "qa"
        / "pause-feature"
        / "2026-06-04T12-00-00Z-corp"
    )
    run_dir.mkdir(parents=True)
    (run_dir / "checkpoint.json").write_text(
        "{ not valid json", encoding="utf-8"
    )

    # Quando implementado: invocar run_qa, assertar stderr contém
    # "3 caminhos" + path do checkpoint + voz mentor calmo (sem ALL-CAPS).
    assert (run_dir / "checkpoint.json").exists()
