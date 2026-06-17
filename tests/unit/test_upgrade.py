"""Tests for engine.upgrade — forge upgrade core logic (tag-based).

TDD: tests reescritos pra refletir a lógica tag-to-tag.

feature-forge faz upgrade da última RELEASE TAG (v*), não do origin/main.
O install deixa o repo em detached HEAD numa tag; o upgrade faz
fetch --tags + checkout da tag mais nova.

Spec §3 D.2. Plan Task 4.4.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


def test_upgrade_no_op_when_at_latest_tag(tmp_path: Path) -> None:
    """When HEAD already equals the latest tag, upgrade is a no-op (return 0, no checkout)."""
    from engine.upgrade import run_upgrade

    with patch("engine.upgrade._git_current_sha", return_value="abc1234"), \
         patch("engine.upgrade._git_fetch"), \
         patch("engine.upgrade._latest_local_tag", return_value="v1.4.0"), \
         patch("engine.upgrade._tag_sha", return_value="abc1234"), \
         patch("engine.upgrade._git_checkout") as checkout:
        result = run_upgrade(forge_home=tmp_path)

    assert result == 0, f"expected 0 (already at latest tag), got {result}"
    checkout.assert_not_called()


def test_upgrade_no_op_when_no_tags(tmp_path: Path) -> None:
    """When no release tag exists, upgrade is a no-op with a warning (return 0, no checkout)."""
    from engine.upgrade import run_upgrade

    with patch("engine.upgrade._git_current_sha", return_value="abc1234"), \
         patch("engine.upgrade._git_fetch"), \
         patch("engine.upgrade._latest_local_tag", return_value=None), \
         patch("engine.upgrade._git_checkout") as checkout:
        result = run_upgrade(forge_home=tmp_path)

    assert result == 0, f"expected 0 (no tags, no-op), got {result}"
    checkout.assert_not_called()


def test_upgrade_rollback_on_smoke_fail(tmp_path: Path) -> None:
    """When smoke check fails after checkout, rollback checkout is called and exit != 0."""
    from engine.upgrade import run_upgrade

    with patch("engine.upgrade._git_current_sha", return_value="abc1234"), \
         patch("engine.upgrade._git_fetch"), \
         patch("engine.upgrade._latest_local_tag", return_value="v1.4.1"), \
         patch("engine.upgrade._tag_sha", return_value="def5678"), \
         patch("engine.upgrade._pip_refresh"), \
         patch("engine.upgrade._smoke_version", return_value=False), \
         patch("engine.upgrade._git_checkout") as checkout:
        result = run_upgrade(forge_home=tmp_path)

    assert result == 4, f"expected 4 on smoke failure + rollback, got {result}"
    # checkout called at least twice: once forward to tag, once back to prev_sha
    assert checkout.call_count >= 2, (
        f"expected forward + rollback checkout, got {checkout.call_count} calls"
    )
    # last checkout must be the rollback to prev_sha
    last_call_args = checkout.call_args_list[-1]
    assert "abc1234" in last_call_args.args, (
        f"rollback checkout did not target prev_sha. calls={checkout.call_args_list}"
    )


def test_upgrade_success(tmp_path: Path) -> None:
    """When a newer tag exists and smoke passes, return 0 and checkout the tag."""
    from engine.upgrade import run_upgrade

    with patch("engine.upgrade._git_current_sha", return_value="abc1234"), \
         patch("engine.upgrade._git_fetch"), \
         patch("engine.upgrade._latest_local_tag", return_value="v1.4.1"), \
         patch("engine.upgrade._tag_sha", return_value="def5678"), \
         patch("engine.upgrade._pip_refresh"), \
         patch("engine.upgrade._smoke_version", return_value=True), \
         patch("engine.upgrade._git_checkout") as checkout:
        result = run_upgrade(forge_home=tmp_path)

    assert result == 0, f"expected 0 on successful upgrade, got {result}"
    # single forward checkout to the latest tag, no rollback
    checkout.assert_called_once()
    assert "v1.4.1" in checkout.call_args.args, (
        f"expected checkout of v1.4.1, got {checkout.call_args}"
    )
