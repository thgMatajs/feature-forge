"""E2E — `forge implement` gate enforcement.

Skipped unless RUN_E2E=1. Validates that the implement command refuses to
proceed when no readiness contract is present (no `.claude/` scaffolding).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

_RUN_E2E = os.environ.get("RUN_E2E") == "1"
_FORGE_HOME = Path(__file__).resolve().parents[2]


@pytest.mark.e2e
@pytest.mark.skipif(not _RUN_E2E, reason="set RUN_E2E=1 to run e2e tests")
def test_forge_implement_refuses_without_workflow_config(tmp_project_root):
    env = os.environ.copy()
    env["FORGE_HOME"] = str(_FORGE_HOME)
    env["PYTHONPATH"] = str(_FORGE_HOME) + os.pathsep + env.get("PYTHONPATH", "")
    rc = subprocess.run(
        [sys.executable, "-m", "engine.cli", "implement", "feature-x"],
        cwd=tmp_project_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        input="",
    )
    # Without a workflow-config the command must abort.
    assert rc.returncode != 0


@pytest.mark.e2e
@pytest.mark.skipif(not _RUN_E2E, reason="set RUN_E2E=1 to run e2e tests")
def test_implement_module_imports_cleanly():
    env = os.environ.copy()
    env["FORGE_HOME"] = str(_FORGE_HOME)
    env["PYTHONPATH"] = str(_FORGE_HOME) + os.pathsep + env.get("PYTHONPATH", "")
    rc = subprocess.run(
        [sys.executable, "-c", "import engine.implement; print('ok')"],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert rc.returncode == 0
