"""E2E — `forge plan {slug}` end-to-end.

Skipped unless RUN_E2E=1. The plan command is also heavily interactive (4
waves of conductor prompts); this test verifies the help / argv handling and
that the plan module imports cleanly under subprocess (no top-level errors).
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
def test_forge_plan_help_in_greenfield_returns_nonzero(tmp_project_root):
    """Plan requires an existing workflow-config — running plan in a
    greenfield (no `.claude/`) must fail gracefully.
    """
    env = os.environ.copy()
    env["FORGE_HOME"] = str(_FORGE_HOME)
    env["PYTHONPATH"] = str(_FORGE_HOME) + os.pathsep + env.get("PYTHONPATH", "")
    rc = subprocess.run(
        [sys.executable, "-m", "engine.cli", "plan", "ghost-slug"],
        cwd=tmp_project_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        input="",
    )
    # No project root → exit 2 / abort path.
    assert rc.returncode != 0


@pytest.mark.e2e
@pytest.mark.skipif(not _RUN_E2E, reason="set RUN_E2E=1 to run e2e tests")
def test_plan_module_imports_cleanly():
    env = os.environ.copy()
    env["FORGE_HOME"] = str(_FORGE_HOME)
    env["PYTHONPATH"] = str(_FORGE_HOME) + os.pathsep + env.get("PYTHONPATH", "")
    # `python -c "import engine.plan"` must succeed.
    rc = subprocess.run(
        [sys.executable, "-c", "import engine.plan; print('ok')"],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert rc.returncode == 0
    assert "ok" in rc.stdout
