"""Tests for engine.upgrade — forge upgrade core logic.

TDD: module created after RED phase confirmed failure.

Spec §3 D.2. Plan Task 4.4.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


def test_upgrade_no_op_when_at_latest(tmp_path: Path) -> None:
    """When HEAD already equals origin/main, upgrade is a no-op (return 0, no pull)."""
    from engine.upgrade import run_upgrade

    with patch("engine.upgrade._git_current_sha", return_value="abc1234"), \
         patch("engine.upgrade._git_fetch"), \
         patch("engine.upgrade._git_head_eq_origin", return_value=True), \
         patch("engine.upgrade._git_pull") as pull:
        result = run_upgrade(forge_home=tmp_path)

    assert result == 0, f"expected 0 (already at latest), got {result}"
    pull.assert_not_called()


def test_upgrade_rollback_on_smoke_fail(tmp_path: Path) -> None:
    """When smoke check fails after pull, git reset is called and exit != 0."""
    from engine.upgrade import run_upgrade

    with patch("engine.upgrade._git_current_sha", return_value="abc1234"), \
         patch("engine.upgrade._git_fetch"), \
         patch("engine.upgrade._git_head_eq_origin", return_value=False), \
         patch("engine.upgrade._git_pull"), \
         patch("engine.upgrade._pip_refresh"), \
         patch("engine.upgrade._smoke_version", return_value=False), \
         patch("engine.upgrade._git_reset_hard") as reset:
        result = run_upgrade(forge_home=tmp_path)

    assert result != 0, "expected non-zero exit on smoke failure"
    reset.assert_called_once()


def test_upgrade_success(tmp_path: Path) -> None:
    """When not at latest and smoke passes, return 0 and do NOT call reset."""
    from engine.upgrade import run_upgrade

    with patch("engine.upgrade._git_current_sha", return_value="abc1234"), \
         patch("engine.upgrade._git_fetch"), \
         patch("engine.upgrade._git_head_eq_origin", return_value=False), \
         patch("engine.upgrade._git_pull"), \
         patch("engine.upgrade._pip_refresh"), \
         patch("engine.upgrade._smoke_version", return_value=True), \
         patch("engine.upgrade._git_reset_hard") as reset:
        result = run_upgrade(forge_home=tmp_path)

    assert result == 0, f"expected 0 on successful upgrade, got {result}"
    reset.assert_not_called()
