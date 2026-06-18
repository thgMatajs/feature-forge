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


def test_upgrade_no_op_when_no_tags(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """When no release tag exists, upgrade is a no-op with a warning (return 0, no checkout)."""
    from engine.upgrade import run_upgrade

    with patch("engine.upgrade._git_current_sha", return_value="abc1234"), \
         patch("engine.upgrade._git_fetch"), \
         patch("engine.upgrade._latest_local_tag", return_value=None), \
         patch("engine.upgrade._git_checkout") as checkout:
        result = run_upgrade(forge_home=tmp_path)

    assert result == 0, f"expected 0 (no tags, no-op), got {result}"
    checkout.assert_not_called()
    # O branch sem tags precisa avisar o usuário (não silenciar). Ancora num
    # substring estável da mensagem de engine/upgrade.py (no-tags branch).
    captured = capsys.readouterr()
    assert "nenhuma release tag encontrada" in captured.out, (
        f"expected no-tags warning on stdout, got: {captured.out!r}"
    )


def test_upgrade_rollback_on_smoke_fail(tmp_path: Path, capsys) -> None:
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

    # C3 EXIT-2-COLLISION: return 4 colapsou em exit 1 + tag [FORGE-ERR:UPGRADE-FAILED].
    assert result == 1, f"expected 1 on smoke failure + rollback, got {result}"
    # WR-01: trava a CATEGORIA do erro, não só o código. ==1 sozinho passaria
    # pra qualquer falha; a tag prova que é o caminho upgrade-failed.
    captured = capsys.readouterr()
    assert "[FORGE-ERR:UPGRADE-FAILED]" in captured.err, (
        f"expected UPGRADE-FAILED tag on stderr, got: {captured.err!r}"
    )
    # checkout called at least twice: once forward to tag, once back to prev_sha
    assert checkout.call_count >= 2, (
        f"expected forward + rollback checkout, got {checkout.call_count} calls"
    )
    # first checkout must be the forward move to the target tag — garante que
    # a sequência completa (forward THEN rollback) é verificada, não só o fim.
    first_call_args = checkout.call_args_list[0]
    assert "v1.4.1" in first_call_args.args, (
        f"forward checkout did not target the release tag. calls={checkout.call_args_list}"
    )
    # last checkout must be the rollback to prev_sha
    last_call_args = checkout.call_args_list[-1]
    assert "abc1234" in last_call_args.args, (
        f"rollback checkout did not target prev_sha. calls={checkout.call_args_list}"
    )


def test_upgrade_rollback_on_pip_fail_re_runs_pip(tmp_path: Path, capsys) -> None:
    """When pip refresh fails after checkout, rollback restores BOTH code and venv.

    Simetria com o path de smoke-fail: o rollback faz git checkout pro prev_sha
    E re-roda pip refresh, restaurando o venv ao estado do sha anterior (que
    funcionava). _pip_refresh falha na 1ª chamada (o refresh da nova tag) e
    sucede na 2ª (o re-refresh do rollback).
    """
    from engine.upgrade import run_upgrade

    pip_calls = {"n": 0}

    def pip_side_effect(*_args, **_kwargs):
        pip_calls["n"] += 1
        if pip_calls["n"] == 1:
            import subprocess

            raise subprocess.CalledProcessError(1, ["pip", "install"])
        # 2ª chamada (re-refresh do rollback) sucede
        return None

    with patch("engine.upgrade._git_current_sha", return_value="abc1234"), \
         patch("engine.upgrade._git_fetch"), \
         patch("engine.upgrade._latest_local_tag", return_value="v1.4.1"), \
         patch("engine.upgrade._tag_sha", return_value="def5678"), \
         patch("engine.upgrade._smoke_version", return_value=True), \
         patch("engine.upgrade._pip_refresh", side_effect=pip_side_effect) as pip, \
         patch("engine.upgrade._git_checkout") as checkout:
        result = run_upgrade(forge_home=tmp_path)

    # C3 EXIT-2-COLLISION: return 4 colapsou em exit 1 + tag [FORGE-ERR:UPGRADE-FAILED].
    assert result == 1, f"expected 1 on pip failure + rollback, got {result}"
    # WR-01: trava a CATEGORIA do erro via tag, não só o código.
    captured = capsys.readouterr()
    assert "[FORGE-ERR:UPGRADE-FAILED]" in captured.err, (
        f"expected UPGRADE-FAILED tag on stderr, got: {captured.err!r}"
    )
    # rollback checkout pro prev_sha aconteceu
    assert checkout.call_count >= 2, (
        f"expected forward + rollback checkout, got {checkout.call_count} calls"
    )
    last_call_args = checkout.call_args_list[-1]
    assert "abc1234" in last_call_args.args, (
        f"rollback checkout did not target prev_sha. calls={checkout.call_args_list}"
    )
    # pip foi chamado DUAS vezes: refresh da nova tag (falhou) + re-refresh do rollback
    assert pip.call_count == 2, (
        f"expected pip refresh re-run during rollback (2 calls), got {pip.call_count}"
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
