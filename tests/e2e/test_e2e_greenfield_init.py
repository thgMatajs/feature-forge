"""E2E — `forge init` on a fresh greenfield project.

Drives the CLI as a subprocess, feeding it canned answers on stdin. Skipped
by default unless `RUN_E2E=1` is set in the environment.

Because `forge init` is heavily interactive (16 steps, dynamic prompts), this
test only verifies the bare entry path: the help arg returns 0 cleanly, and
unknown args return 2. The full interactive script is exercised manually
via the docs/ux/forge-init-roteiro.md walkthrough — automating the entire
flow would couple the test to UI copy too tightly to be maintainable.
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
def test_forge_help_exits_zero(tmp_path):
    env = os.environ.copy()
    env["FORGE_HOME"] = str(_FORGE_HOME)
    env["PYTHONPATH"] = str(_FORGE_HOME) + os.pathsep + env.get("PYTHONPATH", "")
    rc = subprocess.run(
        [sys.executable, "-m", "engine.cli", "--help"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert rc.returncode == 0
    assert "Subcomandos" in rc.stdout or "forge" in rc.stdout


@pytest.mark.e2e
@pytest.mark.skipif(not _RUN_E2E, reason="set RUN_E2E=1 to run e2e tests")
def test_forge_version_exits_zero(tmp_path):
    env = os.environ.copy()
    env["FORGE_HOME"] = str(_FORGE_HOME)
    env["PYTHONPATH"] = str(_FORGE_HOME) + os.pathsep + env.get("PYTHONPATH", "")
    rc = subprocess.run(
        [sys.executable, "-m", "engine.cli", "--version"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert rc.returncode == 0
    assert "forge" in rc.stdout


@pytest.mark.e2e
@pytest.mark.skipif(not _RUN_E2E, reason="set RUN_E2E=1 to run e2e tests")
def test_forge_init_rejects_unknown_arg(tmp_project_root):
    env = os.environ.copy()
    env["FORGE_HOME"] = str(_FORGE_HOME)
    env["PYTHONPATH"] = str(_FORGE_HOME) + os.pathsep + env.get("PYTHONPATH", "")
    rc = subprocess.run(
        [sys.executable, "-m", "engine.cli", "init", "bogus"],
        cwd=tmp_project_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    # Either rejects the arg (exit 2) or prints help — the engine refuses
    # unknown args explicitly with exit 2 per cli.py.
    assert rc.returncode == 2
