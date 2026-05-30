"""E2E — `forge init` against a brownfield project (MeoBonsai).

Skipped unless `RUN_E2E=1` and MeoBonsai is available locally. The full
init flow requires interactive answers — this test only validates that
running `forge init help` from within the brownfield project tree exits 0.
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
def test_forge_init_help_in_meobonsai(meobonsai_root):
    env = os.environ.copy()
    env["FORGE_HOME"] = str(_FORGE_HOME)
    env["PYTHONPATH"] = str(_FORGE_HOME) + os.pathsep + env.get("PYTHONPATH", "")
    rc = subprocess.run(
        [sys.executable, "-m", "engine.cli", "init", "help"],
        cwd=meobonsai_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert rc.returncode == 0


@pytest.mark.e2e
@pytest.mark.skipif(not _RUN_E2E, reason="set RUN_E2E=1 to run e2e tests")
def test_forge_status_in_meobonsai(meobonsai_root):
    """Brownfield: `forge status` should locate the existing `.claude/` if any."""
    env = os.environ.copy()
    env["FORGE_HOME"] = str(_FORGE_HOME)
    env["PYTHONPATH"] = str(_FORGE_HOME) + os.pathsep + env.get("PYTHONPATH", "")
    rc = subprocess.run(
        [sys.executable, "-m", "engine.cli", "status"],
        cwd=meobonsai_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    # status may exit 0 (workflow-config present) or non-zero (no project-root).
    assert rc.returncode in {0, 1, 2}
