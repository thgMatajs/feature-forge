"""Integration test — `forge init` greenfield smoke test.

Drives the `_is_git_repo` and project-root-detection helpers and verifies that
on a fresh greenfield tree, `find_project_root` reports the expected absence
of `.claude/workflow-config.yaml`. The full interactive pipeline is exercised
in `tests/e2e/test_e2e_greenfield_init.py` via subprocess (skipped on rapid CI).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from engine.utils import paths


@pytest.mark.integration
def test_greenfield_project_has_no_workflow_config(tmp_project_root):
    assert paths.try_find_project_root(tmp_project_root) is None


@pytest.mark.integration
def test_init_run_with_help_arg_returns_zero(tmp_project_root, monkeypatch, capsys):
    from engine import init as init_mod

    monkeypatch.chdir(tmp_project_root)
    rc = init_mod.run(["help"])
    assert rc == 0


@pytest.mark.integration
def test_init_run_rejects_unknown_arg(tmp_project_root, monkeypatch, capsys):
    from engine import init as init_mod

    monkeypatch.chdir(tmp_project_root)
    rc = init_mod.run(["bogus"])
    assert rc == 2


@pytest.mark.integration
def test_claude_dir_scaffold_locations(tmp_forge_project):
    # Sanity for the fixture used by other integration tests.
    assert (tmp_forge_project / ".claude" / "memory" / "L1").is_dir()
    assert (tmp_forge_project / ".claude" / "memory" / "L1" / "archived").is_dir()
    assert (tmp_forge_project / ".claude" / "cards").is_dir()
    assert (tmp_forge_project / ".claude" / "inventory").is_dir()
    assert (tmp_forge_project / ".claude" / "hooks").is_dir()
