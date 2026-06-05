"""Integration — task scope lifecycle (TASK-NNNN resolução isolada).

Wave 8 Task 8.2: ``run_qa`` com scope=task exerce o ramo
``raw_target.startswith("TASK-")`` em ``resolve_scope``. Cobre:

- Happy path: TASK-0001 válida → resolve + run tree criada
- Finding ``validator-claim`` com ``sandbox_result`` (Phase 3 result)
  preenchido → contribui pro verdict synthesis
- Task missing → ``ScopeMissingError`` capturado pelo handler (exit 0
  silencioso, mensagem em stderr)

Anti-padrão: subir feature inteira pra cada test — só os arquivos
necessários pra scope task resolver.

Marker: integration (slow). Excluído da rapid lane.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.integration


def _make_task_project(
    tmp_path: Path, *, feature_slug: str, task_id: str
) -> Path:
    """Cria estrutura mínima com 1 task em 1 feature.

    Layout: ``docs/feature-implementation-workflow/features/<slug>/tasks/<id>.yaml``
    """
    proj = tmp_path / "qa-task-pilot"
    (proj / ".git").mkdir(parents=True)
    feature_dir = (
        proj
        / "docs"
        / "feature-implementation-workflow"
        / "features"
        / feature_slug
    )
    tasks_dir = feature_dir / "tasks"
    tasks_dir.mkdir(parents=True)
    (tasks_dir / f"{task_id}.yaml").write_text(
        f"schema-version: 1\nid: {task_id}\ndescription: stub\n",
        encoding="utf-8",
    )
    return proj


def _validator_claim_finding(task_id: str) -> dict[str, Any]:
    """Finding shape canônico do auditor validator-claim com sandbox_result.

    Vector ``validator-claim`` + sandbox_result preenchido (Phase 3 escreve
    isto após executar o exercise). Severity=high → contribui pro verdict
    (high=1 → FLAG, isolado).
    """
    return {
        "vector": "validator-claim",
        "severity": "high",
        "title": "claim sem exercise correspondente",
        "description": (
            f"task {task_id} declara validator novo sem sandbox demonstrando "
            "bloqueio efetivo."
        ),
        "scope": {"files": [f"tasks/{task_id}.yaml"]},
        "evidence": {"claim_path": f"tasks/{task_id}.yaml"},
        "sandbox_result": {
            "executable": True,
            "verdict": "claim-failed",
            "evidence": "sandbox rodou sem assert do comportamento prometido",
            "duration_seconds": 0.4,
        },
        "proposed_evolution": {
            "type": "qa-finding-validator-claim",
            "summary": "claim validator sem exercise — task " + task_id,
        },
    }


def test_qa_task_scope_resolves_and_creates_run_tree(tmp_path: Path) -> None:
    """Happy path: TASK-0001 resolve, run tree criada, handoff escrito."""
    from engine.qa import run_qa

    task_id = "TASK-0001"
    proj = _make_task_project(tmp_path, feature_slug="task-host", task_id=task_id)
    workflow_config = {"qa": {"enabled": True}}

    exit_code = run_qa(task_id, project_root=proj, workflow_config=workflow_config)
    assert exit_code == 0

    qa_root = proj / ".planning" / "qa" / task_id
    assert qa_root.is_dir()
    run_dirs = list(qa_root.iterdir())
    assert len(run_dirs) == 1
    handoff_path = run_dirs[0] / "conductor-handoff.json"
    assert handoff_path.is_file()
    import json as _json

    handoff = _json.loads(handoff_path.read_text(encoding="utf-8"))
    assert handoff["scope"]["type"] == "task"
    assert handoff["scope"]["target"] == task_id


def test_qa_task_scope_finding_with_sandbox_result_contributes_verdict(
    tmp_path: Path,
) -> None:
    """Finding validator-claim com sandbox_result → verdict synthesis."""
    from engine.qa.emit import emit_proposed_evolutions
    from engine.qa.synthesis import synthesize

    task_id = "TASK-0002"
    proj = _make_task_project(tmp_path, feature_slug="task-host", task_id=task_id)

    finding = _validator_claim_finding(task_id)
    result = synthesize([finding])

    # high=1 → FLAG (§5.4)
    assert result.verdict == "FLAG"
    assert result.by_severity["high"] == 1
    assert result.by_vector.get("validator-claim") == 1

    # Sandbox result preservado no payload deduplicado
    assert result.findings[0]["sandbox_result"]["executable"] is True
    assert result.findings[0]["sandbox_result"]["verdict"] == "claim-failed"

    # Emit cria entry actionable (high é actionable per Phase 5)
    summary = emit_proposed_evolutions(result.findings, project_root=proj)
    assert summary["written"] == 1
    assert summary["write_failed"] is False


def test_qa_task_scope_missing_task_returns_zero_with_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """TASK-9999 inexistente → ScopeMissingError absorvido, exit 0, stderr."""
    from engine.qa import run_qa

    proj = _make_task_project(
        tmp_path, feature_slug="task-host", task_id="TASK-0001"
    )
    workflow_config = {"qa": {"enabled": True}}

    # TASK-9999 não existe → handler captura ScopeMissingError + exit 0
    # (§ run_qa docstring: "ScopeError absorvido, mensagem em stderr").
    exit_code = run_qa(
        "TASK-9999", project_root=proj, workflow_config=workflow_config
    )
    assert exit_code == 0  # NÃO 8 — scope error é informativo, não bloqueia

    captured = capsys.readouterr()
    # Mensagem em stderr com mentor calmo (sem ALL-CAPS, sem emoji decorativo)
    assert "TASK-9999" in captured.err
    assert "nao encontrada" in captured.err.lower() or "não encontrada" in captured.err.lower()
