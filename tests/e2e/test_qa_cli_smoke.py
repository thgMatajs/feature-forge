"""E2E — `forge qa` CLI smoke.

Drives the CLI as a subprocess para garantir que o handler ``engine.qa.run_qa``
seja booteado pelo dispatcher real (``engine.cli``) sem tropecar em import,
arg parsing, ou resolucao de project root. Cobre apenas o boot/dispatch path —
phases 1, 2, 4 dependem de LLM dispatch externo (qa-conductor), entao o smoke
para na mensagem "Dispatch agents/qa-conductor.md pra rodar phases 1-4"
emitida quando ``findings/`` esta vazio.

Skipped por default; ativa com ``RUN_E2E=1`` no env (mesmo gate dos demais
testes em ``tests/e2e/``).

Cenarios:
- ``test_forge_qa_cli_invokes_handler`` — happy path: tmp_project com feature
  minima, ``qa.enabled: true``, subprocess ``forge qa <slug>`` retorna exit 0
  e stdout reporta run tree criada.
- ``test_forge_qa_disabled_returns_clean`` — disabled path: ``qa.enabled:
  false`` no workflow-config, subprocess retorna exit 0 e stderr contem
  "desabilitado" (mensagem mentor-calmo do handler).

Voz mentor calmo nos asserts — falha clara, sem alarmismo.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_RUN_E2E = os.environ.get("RUN_E2E") == "1"
_FORGE_HOME = Path(__file__).resolve().parents[2]


def _env_with_forge_home() -> dict[str, str]:
    """Env enriquecido com FORGE_HOME + PYTHONPATH apontando pro worktree atual.

    Mirror do pattern usado em ``test_e2e_greenfield_init.py`` —
    garante que o subprocess Python encontre ``engine.*`` sem ``pip install``.
    """
    env = os.environ.copy()
    env["FORGE_HOME"] = str(_FORGE_HOME)
    env["PYTHONPATH"] = (
        str(_FORGE_HOME) + os.pathsep + env.get("PYTHONPATH", "")
    )
    return env


def _write_workflow_config(project_root: Path, *, enabled: bool) -> None:
    """Escreve ``.claude/workflow-config.yaml`` minimo com ``qa.enabled``.

    Args:
        project_root: raiz do tmp_project (recebe ``.claude/`` se ausente).
        enabled: valor pra ``qa.enabled`` no YAML.
    """
    claude = project_root / ".claude"
    claude.mkdir(parents=True, exist_ok=True)
    enabled_literal = "true" if enabled else "false"
    (claude / "workflow-config.yaml").write_text(
        f"qa:\n  enabled: {enabled_literal}\n",
        encoding="utf-8",
    )


@pytest.mark.e2e
@pytest.mark.skipif(not _RUN_E2E, reason="set RUN_E2E=1 to run e2e tests")
def test_forge_qa_cli_invokes_handler(tmp_path):
    """Happy: subprocess ``forge qa <slug>`` boota handler e cria run tree.

    Sem findings preenchidos, o handler escreve ``conductor-handoff.json`` e
    retorna exit 0 com mensagem "Dispatch agents/qa-conductor.md". Esse e o
    contrato de boot exposto pelo CLI — phases 1+2+4 ficam pro orchestrator
    externo. O smoke confirma so que CLI -> handler -> Phase 0 -> conductor
    handoff funciona sem regressao.
    """
    # Project root: .git/ + .claude/workflow-config.yaml + feature minima.
    (tmp_path / ".git").mkdir()
    _write_workflow_config(tmp_path, enabled=True)

    slug = "example"
    feature_dir = (
        tmp_path
        / "docs"
        / "feature-implementation-workflow"
        / "features"
        / slug
    )
    feature_dir.mkdir(parents=True)

    rc = subprocess.run(
        [sys.executable, "-m", "engine.cli", "qa", slug],
        cwd=tmp_path,
        env=_env_with_forge_home(),
        capture_output=True,
        text=True,
        timeout=120,
    )

    # Exit code: 0 (conductor dispatch pendente, sem findings) ou 8 (BLOCK
    # caso findings ja existam). Ambos sao caminhos validos contratuais do
    # handler — smoke nao escreve findings, entao espera 0 normalmente.
    assert rc.returncode in (0, 8), (
        f"forge qa retornou {rc.returncode} (esperava 0 ou 8).\n"
        f"stdout: {rc.stdout}\nstderr: {rc.stderr}"
    )

    # Confirma que chegou no handler — stdout deve mencionar run tree ou
    # verdict (depende de qual branch executou). Lowercase pra robustez
    # contra mudanca de capitalizacao na mensagem.
    out_lower = rc.stdout.lower()
    assert (
        "forge qa" in out_lower
        or "verdict" in out_lower
        or "conductor" in out_lower
        or "run tree" in out_lower
    ), (
        "stdout nao contem nenhum marcador esperado do handler qa.\n"
        f"stdout: {rc.stdout}\nstderr: {rc.stderr}"
    )

    # CONF-007: valida qa-report.json on-disk per SDD §15.4.
    # Phase 0 deve ter escrito o skeleton com verdict=pending; quando
    # findings existem, Phase 4 finaliza com PASS/FLAG/BLOCK.
    qa_runs_root = tmp_path / ".planning" / "qa"
    reports = list(qa_runs_root.rglob("qa-report.json"))
    assert len(reports) >= 1, (
        f"qa-report.json nao encontrado em {qa_runs_root}.\n"
        f"stdout: {rc.stdout}\nstderr: {rc.stderr}"
    )
    report = json.loads(reports[0].read_text(encoding="utf-8"))
    assert "schema_version" in report, (
        f"qa-report.json sem schema_version: {report}"
    )
    assert "run" in report, f"qa-report.json sem envelope 'run': {report}"
    assert "id" in report["run"], (
        f"qa-report.json sem run.id (canonico per qa-report.md): {report}"
    )
    assert report["verdict"] in {"pending", "PASS", "FLAG", "BLOCK"}, (
        f"verdict invalido: {report.get('verdict')}"
    )
    assert "scope" in report["run"], (
        f"qa-report.json sem run.scope: {report}"
    )
    assert "type" in report["run"]["scope"]
    assert "started_at" in report["run"]
    assert report["run"]["started_at"].endswith("Z"), (
        f"started_at precisa terminar com Z (UTC): "
        f"{report['run']['started_at']}"
    )
    assert "config_snapshot" in report["run"], (
        f"qa-report.json sem run.config_snapshot (audit trail): {report}"
    )
    assert isinstance(report.get("findings"), list), (
        f"findings deve ser list: {type(report.get('findings'))}"
    )


@pytest.mark.e2e
@pytest.mark.skipif(not _RUN_E2E, reason="set RUN_E2E=1 to run e2e tests")
def test_forge_qa_disabled_returns_clean(tmp_path):
    """Disabled: ``qa.enabled: false`` -> exit 0 + stderr menciona desabilitado.

    Handler curto-circuita antes do scope resolve, entao o slug pode ate nem
    existir — o caminho disabled e checado primeiro. Garante que opt-out via
    workflow-config nao quebra CLI nem propaga exit code de erro.
    """
    (tmp_path / ".git").mkdir()
    _write_workflow_config(tmp_path, enabled=False)

    rc = subprocess.run(
        [sys.executable, "-m", "engine.cli", "qa", "nonexistent-slug"],
        cwd=tmp_path,
        env=_env_with_forge_home(),
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert rc.returncode == 0, (
        f"forge qa disabled retornou {rc.returncode} (esperava 0).\n"
        f"stdout: {rc.stdout}\nstderr: {rc.stderr}"
    )
    assert "desabilitado" in rc.stderr.lower(), (
        "stderr nao contem 'desabilitado' — mensagem do opt-out path "
        "regrediu ou nao foi emitida.\n"
        f"stderr: {rc.stderr}"
    )

    # CONF-007: qa.enabled=false NAO deve criar qa-report.json.
    # Phase 0 nem roda quando desabilitado — nenhum artefato de run e
    # persistido.
    qa_runs_root = tmp_path / ".planning" / "qa"
    reports = (
        list(qa_runs_root.rglob("qa-report.json"))
        if qa_runs_root.exists()
        else []
    )
    assert reports == [], (
        f"qa-report.json nao deveria existir com qa.enabled=false, "
        f"mas achei: {reports}"
    )
