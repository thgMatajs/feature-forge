"""Integration — hook auto-run on feature-done em engine.implement.

Wave 7 Task 7.2: stub mínimo confirmando que o hook respeita os toggles
de workflow-config e oferece 3-caminhos quando opt-in está ativo.
Coverage profundo (3-caminhos branches, exit code propagation,
status-log entries) vem em Wave 8.4.

Marker: integration (slow). Excluído da rapid CI lane.
"""

from __future__ import annotations

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


@pytest.fixture
def qa_hook_project(tmp_path: Path) -> Path:
    proj = tmp_path / "qa-hook-pilot"
    (proj / ".claude").mkdir(parents=True)
    return proj


def test_hook_noop_when_qa_disabled(qa_hook_project: Path) -> None:
    """qa.enabled=false → hook retorna sem prompt nem dispatch."""
    from engine.implement import _maybe_run_qa_pre_retrospective

    _write_config(
        qa_hook_project,
        {"enabled": False, "auto-run-on-feature-done": True},
    )

    # Se o hook tentar perguntar 3-caminhos OU invocar run_qa, mocks
    # capturam (não deveriam ser chamados).
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
