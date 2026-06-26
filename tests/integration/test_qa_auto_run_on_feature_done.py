"""Integration — hook auto-run on feature-done em engine.implement.

Wave 7 Task 7.2: stubs mínimos (noop quando qa.enabled=false ou auto-run
desligado).

Wave 8 Task 8.4: expansão dos 4 cenários canônicos do 3-caminhos:

- ``auto-run=true`` + choice="a" (run) → invoca run_qa + grava
  ``qa-auto-run-completed`` em history
- ``auto-run=true`` + choice="b" (skip) → grava ``qa-auto-run-skipped``
- ``auto-run=true`` + choice="c" (disable) → workflow-config persistido
  com ``auto-run-on-feature-done: false`` + history `qa-auto-run-disabled-by-user`
- ``auto-run=false`` (negative): hook nunca dispara prompt/dispatch
  (já coberto pelos stubs noop — preservado)

Anti-padrão: invocar ``input()`` real (sem prompt interativo em CI). Tudo
mockado via ``patch("engine.implement.question.ask_three_paths")``.
Subprocess CLI é Wave 9 (e2e).

Marker: integration (slow). Excluído da rapid CI lane.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml

pytestmark = pytest.mark.integration


def _write_config(project: Path, qa_block: dict[str, Any]) -> Path:
    """Cria `.claude/workflow-config.yaml` com bloco `qa:` específico."""
    cfg_path = project / ".claude" / "workflow-config.yaml"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(
        yaml.safe_dump({"schema-version": 1, "qa": qa_block}), encoding="utf-8"
    )
    return cfg_path


def _read_history(project: Path, feature_slug: str) -> list[dict[str, Any]]:
    """Lê `.claude/forge/state/lifecycle/<slug>/history.jsonl` linha-a-linha."""
    path = (
        project
        / ".claude"
        / "forge"
        / "state"
        / "lifecycle"
        / feature_slug
        / "history.jsonl"
    )
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            entries.append(json.loads(line))
    return entries


@pytest.fixture
def qa_hook_project(tmp_path: Path) -> Path:
    proj = tmp_path / "qa-hook-pilot"
    (proj / ".claude").mkdir(parents=True)
    return proj


# ──────────────────────────────────────────────────────────────────────────
# Wave 7 stubs preservados — negativos (hook não dispara)
# ──────────────────────────────────────────────────────────────────────────


def test_hook_noop_when_qa_disabled(qa_hook_project: Path) -> None:
    """qa.enabled=false → hook retorna sem prompt nem dispatch."""
    from engine.implement import _maybe_run_qa_pre_retrospective

    _write_config(
        qa_hook_project,
        {"enabled": False, "auto-run-on-feature-done": True},
    )

    with patch("engine.implement.question.ask_three_paths") as mock_ask, patch(
        "engine.qa.run_qa"
    ) as mock_run:
        _maybe_run_qa_pre_retrospective("dummy-feature", qa_hook_project)

    assert not mock_ask.called, "ask_three_paths NÃO devia ter sido chamado"
    assert not mock_run.called, "run_qa NÃO devia ter sido chamado"


def test_hook_noop_when_auto_run_disabled(qa_hook_project: Path) -> None:
    """qa.auto-run-on-feature-done=false (default) → hook retorna sem prompt."""
    from engine.implement import _maybe_run_qa_pre_retrospective

    _write_config(
        qa_hook_project,
        {"enabled": True, "auto-run-on-feature-done": False},
    )

    with patch("engine.implement.question.ask_three_paths") as mock_ask, patch(
        "engine.qa.run_qa"
    ) as mock_run:
        _maybe_run_qa_pre_retrospective("dummy-feature", qa_hook_project)

    assert not mock_ask.called
    assert not mock_run.called


# ──────────────────────────────────────────────────────────────────────────
# Wave 8.4 — 3-caminhos branches quando auto-run ativo
# ──────────────────────────────────────────────────────────────────────────


def test_hook_run_choice_dispatches_run_qa_and_logs_completed(
    qa_hook_project: Path,
) -> None:
    """choice="a" (run) → run_qa chamado, history grava qa-auto-run-completed."""
    from engine.implement import _maybe_run_qa_pre_retrospective

    _write_config(
        qa_hook_project,
        {"enabled": True, "auto-run-on-feature-done": True},
    )

    feature_slug = "auto-run-feature"
    with patch(
        "engine.implement.question.ask_three_paths", return_value="a"
    ) as mock_ask, patch("engine.qa.run_qa", return_value=0) as mock_run:
        _maybe_run_qa_pre_retrospective(feature_slug, qa_hook_project)

    assert mock_ask.called, "3-caminhos deveria ter sido perguntado"
    assert mock_run.called, "choice=a deveria disparar run_qa"

    # Confirma kwargs canônicos passados pro run_qa
    kwargs = mock_run.call_args.kwargs
    assert kwargs["project_root"] == qa_hook_project
    assert isinstance(kwargs["workflow_config"], dict)
    args = mock_run.call_args.args
    assert args[0] == feature_slug

    history = _read_history(qa_hook_project, feature_slug)
    kinds = [h.get("kind") for h in history]
    assert "qa-auto-run-completed" in kinds


def test_hook_skip_choice_logs_skipped_and_does_not_dispatch(
    qa_hook_project: Path,
) -> None:
    """choice="b" (skip) → run_qa NÃO chamado, history grava qa-auto-run-skipped."""
    from engine.implement import _maybe_run_qa_pre_retrospective

    _write_config(
        qa_hook_project,
        {"enabled": True, "auto-run-on-feature-done": True},
    )

    feature_slug = "skip-feature"
    with patch(
        "engine.implement.question.ask_three_paths", return_value="b"
    ), patch("engine.qa.run_qa") as mock_run:
        _maybe_run_qa_pre_retrospective(feature_slug, qa_hook_project)

    assert not mock_run.called, "choice=b NÃO deveria disparar run_qa"

    history = _read_history(qa_hook_project, feature_slug)
    kinds = [h.get("kind") for h in history]
    assert "qa-auto-run-skipped" in kinds
    # Reason canônico: "user-choice" (distinto de "user-pause" — pausa via Ctrl+C)
    skip_entry = next(h for h in history if h.get("kind") == "qa-auto-run-skipped")
    assert skip_entry.get("reason") == "user-choice"


def test_hook_disable_choice_persists_workflow_config_toggle(
    qa_hook_project: Path,
) -> None:
    """choice="c" (disable) → workflow-config grava auto-run=false; history log."""
    from engine.implement import _maybe_run_qa_pre_retrospective

    _write_config(
        qa_hook_project,
        {"enabled": True, "auto-run-on-feature-done": True},
    )

    feature_slug = "disable-feature"
    with patch(
        "engine.implement.question.ask_three_paths", return_value="c"
    ), patch("engine.qa.run_qa") as mock_run:
        _maybe_run_qa_pre_retrospective(feature_slug, qa_hook_project)

    assert not mock_run.called, "choice=c NÃO deveria disparar run_qa"

    # workflow-config persistido com toggle off
    cfg_path = qa_hook_project / ".claude" / "workflow-config.yaml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    assert cfg["qa"]["auto-run-on-feature-done"] is False, (
        "toggle deveria ter sido gravado em workflow-config"
    )
    # qa.enabled preservado (toggle só mexeu em auto-run, não no enabled global)
    assert cfg["qa"]["enabled"] is True

    history = _read_history(qa_hook_project, feature_slug)
    kinds = [h.get("kind") for h in history]
    assert "qa-auto-run-disabled-by-user" in kinds
