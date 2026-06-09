"""Integration — Ctrl+C pause + resume (Decisão 27 + CONF-004).

Wave 8 Task 8.6 / CONF-004: contrato pause/resume implementado em
``engine.qa.checkpoint`` + integracao em ``engine.qa.__init__.run_qa``.

Decisao 27 estabelece "pause = ``deferred`` auto-resumable; abort terminal
soh via ``forge undo``". O SIGINT handler em ``run_qa`` escreve
``<run_tree.root>/checkpoint.json`` atomicamente; re-invocacao detecta o
checkpoint via ``find_resumable_run`` e retoma sem criar novo ``run_id``.

Marker: integration (slow). Excluido da rapid lane.
"""

from __future__ import annotations

import json
import signal
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def qa_pause_project(tmp_path: Path) -> Path:
    """Project root minimo com feature stub pra exercicios de pause/resume."""
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


def test_checkpoint_written_on_sigint(qa_pause_project: Path) -> None:
    """SIGINT handler em run_qa escreve checkpoint.json atomicamente.

    Estrategia: ao inves de fork+SIGINT real (frageis em pytest), valida
    o handler invocando-o diretamente apos run_qa instalar via
    ``signal.signal``. Confirma:
    1. ``signal.signal(SIGINT, ...)`` foi chamado (handler instalado)
    2. ``write_checkpoint`` chamado pelo handler com argumentos coerentes
    3. ``signal.signal`` chamado de novo no finally pra restaurar prev_handler
    """
    from engine.qa import run_qa

    workflow_config: dict[str, Any] = {"qa": {"enabled": True}}

    handler_installed: list[Any] = []
    original_signal = signal.signal

    def _capture_signal(sig: int, handler: Any) -> Any:
        if sig == signal.SIGINT:
            handler_installed.append(handler)
        return original_signal(sig, handler)

    with patch("engine.qa.signal.signal", side_effect=_capture_signal):
        # Run completo (sem findings -> exit cedo apos handoff write).
        run_qa(
            "pause-feature",
            project_root=qa_pause_project,
            workflow_config=workflow_config,
        )

    # Handler foi instalado (1a chamada) + restaurado (2a chamada).
    assert len(handler_installed) >= 2
    sigint_handler = handler_installed[0]
    assert callable(sigint_handler)
    assert sigint_handler is not original_signal  # nao e o default

    # Localiza o run dir criado pra confirmar atomic write contract.
    qa_dir = qa_pause_project / ".planning" / "qa" / "pause-feature"
    runs = list(qa_dir.iterdir())
    assert len(runs) == 1
    run_dir = runs[0]

    # Simula SIGINT chamando o handler — deve escrever checkpoint.json
    # e chamar sys.exit(130).
    with pytest.raises(SystemExit) as exc_info:
        sigint_handler(signal.SIGINT, None)
    assert exc_info.value.code == 130

    checkpoint_path = run_dir / "checkpoint.json"
    assert checkpoint_path.exists()
    payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert payload["scope_type"] == "feature"
    assert payload["scope_target"] == "pause-feature"
    assert isinstance(payload["last_phase_completed"], int)
    assert payload["interrupted_at"].endswith("Z")
    assert "run_id" in payload


def test_resume_reuses_existing_run_tree_and_reads_findings(
    qa_pause_project: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Nova invocacao detecta checkpoint + retoma sem novo run_id.

    Pre-seed: run dir + checkpoint pendente + 1 finding em findings/.
    Apos invocar ``run_qa``:
    - Reusa o run dir existente (NAO cria novo run_id)
    - Print contem "Retomando run <run_id>"
    - Phase 4/5 rodam sobre os findings do pre-seed
    """
    from engine.qa import run_qa

    target = "pause-feature"
    existing_run_id = "2026-06-04T12-00-00Z-abcd"
    run_dir = (
        qa_pause_project
        / ".planning"
        / "qa"
        / target
        / existing_run_id
    )
    (run_dir / "findings").mkdir(parents=True)
    (run_dir / "fixtures").mkdir()
    (run_dir / "audit").mkdir()
    (run_dir / "snapshot").mkdir()

    # Finding actionable pra exercitar synthesis + emit
    (run_dir / "findings" / "phase-1-coverage.json").write_text(
        json.dumps(
            {
                "findings": [
                    {
                        "id": "F-1",
                        "vector": "coverage-gap",
                        "severity": "info",
                        "summary": "stub finding",
                        "repro": "stub",
                        "remediation": "stub",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "qa-report.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run": {"id": existing_run_id},
                "verdict": "pending",
                "summary": {},
                "findings": [],
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "checkpoint.json").write_text(
        json.dumps(
            {
                "run_id": existing_run_id,
                "scope_type": "feature",
                "scope_target": target,
                "last_phase_completed": 3,
                "interrupted_at": "2026-06-04T12-30-00Z",
                "findings_partial_count": 1,
            }
        ),
        encoding="utf-8",
    )

    run_qa(
        target,
        project_root=qa_pause_project,
        workflow_config={"qa": {"enabled": True}},
    )

    captured = capsys.readouterr()
    assert "Retomando run" in captured.out
    assert existing_run_id in captured.out

    # Run dir reutilizado: nao deve haver outro irmao
    qa_dir = qa_pause_project / ".planning" / "qa" / target
    runs = list(qa_dir.iterdir())
    assert len(runs) == 1
    assert runs[0].name == existing_run_id

    # qa-report.json foi finalizado (verdict nao mais "pending")
    final = json.loads(
        (run_dir / "qa-report.json").read_text(encoding="utf-8")
    )
    assert final["verdict"] != "pending"

    # Checkpoint foi limpo apos completion
    assert not (run_dir / "checkpoint.json").exists()


def test_corrupt_checkpoint_prints_three_paths_remediation(
    qa_pause_project: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Checkpoint JSON corrupto -> 3-caminhos mentor calmo + return 0.

    Template canonico de Disciplina #1 (CONF-004 H-1):
    - O que falhou / Onde / Por que importa
    - Tres caminhos pra resolver (numerados)
    - Sem auto-fix - escolha humana
    """
    from engine.qa import run_qa

    target = "pause-feature"
    run_dir = (
        qa_pause_project
        / ".planning"
        / "qa"
        / target
        / "2026-06-04T12-00-00Z-corp"
    )
    run_dir.mkdir(parents=True)
    (run_dir / "checkpoint.json").write_text(
        "{ not valid json", encoding="utf-8"
    )
    (run_dir / "qa-report.json").write_text(
        json.dumps({"verdict": "pending"}), encoding="utf-8"
    )

    exit_code = run_qa(
        target,
        project_root=qa_pause_project,
        workflow_config={"qa": {"enabled": True}},
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    stderr = captured.err
    # Header + secoes do template canonico (3-caminhos pattern).
    assert "Checkpoint corrupto" in stderr
    assert "O que falhou:" in stderr
    assert "Onde:" in stderr
    assert "Por que importa:" in stderr
    assert "Tres caminhos pra resolver:" in stderr
    assert "Sem auto-fix" in stderr
    # Os 3 paths numerados.
    assert "1) Ignorar checkpoint" in stderr
    assert "2) Inspecionar" in stderr
    assert "3) Apenas o checkpoint corrompeu" in stderr
    # Path do checkpoint mencionado na secao Onde + Tres caminhos.
    assert str(run_dir / "checkpoint.json") in stderr
    # Caminho 3 NAO sugere .bak (checkpoint nunca cria backup).
    assert ".bak" not in stderr
    # Voz mentor calmo: sem ALL-CAPS, sem "ERROR!!!"
    assert "ERROR" not in stderr
    assert "!!!" not in stderr
